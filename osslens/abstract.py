"""L3 抽象编排：cluster_run / reconcile、run 记录、成本闸门、零 LLM 降级。

依据：L3 卡 T5/T6/T8/T9、规律库与范围配置 v0.2 §D–§G、设计方案 v1.4 §9。

★ 时间只来自 `as_of`（不用运行时钟），run_id 由输入确定性派生 → 编排幂等、可重放。
★ 样本未达 S1 阈值 → `insufficient_samples` 合法终态、产 0 条、0 次 LLM（S4）。
★ 抽象 run 才允许调用模型，且必须先过预算闸门；off 档 / 无凭据一律零调用。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .config import Config, Layout
from .depth import (
    EVENT_BLOCKED,
    EVENT_CACHE_HIT,
    EVENT_CALL,
    EVENT_DOWNGRADE,
    CostEvent,
    compute_quota,
    estimate_cost,
    load_events,
    record_event,
)
from .llm import estimate_tokens
from .patterns import (
    Evidence,
    Op,
    PatternEntry,
    PatternError,
    ProjectFeatures,
    RecallResult,
    SelfCheck,
    append_ops,
    apply_ops,
    assert_storable,
    build_self_check,
    load_library,
    needs_reconcile,
    recall,
    save_library,
    should_cross_domain,
)
from .util import (
    append_jsonl,
    as_dict,
    as_int,
    as_list,
    as_str,
    atomic_write_text,
    fmt_iso,
    read_jsonl,
    sha256_text,
    stable_json,
)

STATUS_COMPLETED = "completed"
STATUS_INSUFFICIENT = "insufficient_samples"
STATUS_NO_CREDENTIALS = "no_credentials"
STATUS_BUDGET_BLOCKED = "budget_blocked"
STATUS_DEGRADED = "degraded"

TYPE_CLUSTER = "cluster-abstraction"
TYPE_RECONCILE = "reconcile"
TYPE_CROSS_DOMAIN = "cross-domain"

ABSTRACT_REPO = "<abstract>"
CROSS_DOMAIN_CLUSTER = "<cross-domain>"


# --------------------------------------------------------------------------- run 记录


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    type: str
    cluster: str
    trigger: str
    input_projects: tuple[str, ...]
    input_patterns: tuple[str, ...]
    ops: tuple[Op, ...]
    llm_calls: int
    created_at: str
    status: str
    self_check: SelfCheck
    warnings: tuple[str, ...] = ()
    produced_patterns: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "type": self.type,
            "cluster": self.cluster,
            "trigger": self.trigger,
            "input_projects": sorted(self.input_projects),
            "input_patterns": sorted(self.input_patterns),
            "ops": [item.to_json() for item in self.ops],
            "llm_calls": self.llm_calls,
            "created_at": self.created_at,
            "status": self.status,
            "self_check": self.self_check.to_json(),
            "warnings": list(self.warnings),
            "produced_patterns": sorted(self.produced_patterns),
        }

    @classmethod
    def from_json(cls, value: Any) -> RunRecord:
        payload = as_dict(value)
        check = as_dict(payload.get("self_check"))
        return cls(
            run_id=as_str(payload.get("run_id")),
            type=as_str(payload.get("type")),
            cluster=as_str(payload.get("cluster")),
            trigger=as_str(payload.get("trigger")),
            input_projects=tuple(
                sorted(as_str(item) for item in as_list(payload.get("input_projects")))
            ),
            input_patterns=tuple(
                sorted(as_str(item) for item in as_list(payload.get("input_patterns")))
            ),
            ops=tuple(Op.from_json(item) for item in as_list(payload.get("ops"))),
            llm_calls=as_int(payload.get("llm_calls")),
            created_at=as_str(payload.get("created_at")),
            status=as_str(payload.get("status")),
            self_check=SelfCheck(
                has_drilldown_evidence=bool(check.get("q1_has_drilldown_evidence", False)),
                new_counterexamples=as_int(check.get("q2_new_counterexamples")),
                has_cross_domain_evidence=bool(check.get("q3_has_cross_domain_evidence", False)),
                manual_review_target=as_str(check.get("q4_manual_review_target")),
                warnings=tuple(as_str(item) for item in as_list(check.get("warnings"))),
            ),
            warnings=tuple(as_str(item) for item in as_list(payload.get("warnings"))),
            produced_patterns=tuple(
                sorted(as_str(item) for item in as_list(payload.get("produced_patterns")))
            ),
        )


def load_runs(layout: Layout) -> tuple[RunRecord, ...]:
    return tuple(RunRecord.from_json(item) for item in read_jsonl(layout.abstract_runs_jsonl))


def append_run(layout: Layout, record: RunRecord) -> bool:
    """run 记录 append-only；同一 run_id 已存在则跳过（重放不产生重复行）。"""
    if any(item.run_id == record.run_id for item in load_runs(layout)):
        return False
    append_jsonl(layout.abstract_runs_jsonl, record.to_json())
    return True


def run_id_for(*, run_type: str, cluster: str, as_of: datetime, projects: Sequence[str]) -> str:
    return sha256_text(f"{run_type}|{cluster}|{fmt_iso(as_of)}|{','.join(sorted(projects))}")[:16]


# --------------------------------------------------------------------------- 真实样本


@dataclass(frozen=True)
class Sample:
    repo: str
    domain: str | None
    analyzed_at: str
    card: dict[str, Any]


def load_samples(layout: Layout, config: Config) -> tuple[tuple[Sample, ...], tuple[str, ...]]:
    """从 `data/featcards/*.json` 读真实样本；归类缺口单列上报，不自行补规则（L3 卡 §8）。

    同一仓库保留 `analyzed_at` 最新的一张特征卡（确定性排序，不读运行时钟）。
    """
    by_repo: dict[str, Sample] = {}
    for path in sorted(layout.featcards_dir.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(card, dict):
            continue
        repo = as_str(as_dict(card.get("identity")).get("repo"))
        if not repo:
            continue
        sample = Sample(
            repo=repo,
            domain=config.domain_for(repo),
            analyzed_at=as_str(as_dict(card.get("identity")).get("analyzed_at")),
            card=card,
        )
        current = by_repo.get(repo)
        if current is None or sample.analyzed_at >= current.analyzed_at:
            by_repo[repo] = sample
    ordered = tuple(sorted(by_repo.values(), key=lambda item: item.repo))
    uncovered = tuple(sorted(item.repo for item in ordered if item.domain is None))
    return ordered, uncovered


def l2_summary(entries: Sequence[PatternEntry]) -> str:
    """跨域 run 的输入：L2 **结构化摘要**（id + 紧凑字段），绝不含证据/源码正文。"""
    lines = [
        f"{entry.id}|{entry.cluster}|{entry.statement}|tags={','.join(entry.tags)}"
        f"|conf={entry.confidence}|anti={len(entry.counterexamples)}"
        for entry in sorted(entries, key=lambda item: item.id)
        if entry.level == "L2" and entry.status != "falsified"
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- 成本闸门与记账


def budget_gate(
    config: Config, *, as_of: datetime, estimated_prompt_tokens: int
) -> tuple[bool, str]:
    """复用 L2 的估算 × 安全系数闸门（T8），不另造一套成本口径。"""
    adjusted = config.safety_adjusted(estimated_prompt_tokens)
    budget = config.depth.budget
    quota = compute_quota(config, load_events(config.layout), as_of)
    if adjusted > budget.per_run_prompt_tokens:
        return False, f"单次上限 {budget.per_run_prompt_tokens}（估算×系数 {adjusted}）"
    if quota.tokens_week + adjusted > quota.tokens_week_limit:
        return False, f"周预算 {quota.tokens_week}/{quota.tokens_week_limit}"
    if quota.tokens_month + adjusted > quota.tokens_month_limit:
        return False, f"月预算 {quota.tokens_month}/{quota.tokens_month_limit}"
    return True, ""


def _cost_event(
    *,
    event: str,
    run_id: str,
    as_of: datetime,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_hit_tokens: int,
    reason: str,
    purpose: str,
    estimated_cost: float | None,
) -> CostEvent:
    return CostEvent(
        event=event,
        repo=ABSTRACT_REPO,
        depth="fast",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost=estimated_cost,
        source="api" if event == EVENT_CALL else "skipped",
        as_of=fmt_iso(as_of),
        run_id=run_id,
        requested_depth="fast",
        actual_depth="fast",
        reason=reason,
        cache_hit_tokens=cache_hit_tokens,
        purpose=purpose,
    )


# --------------------------------------------------------------------------- 模型调用者（可注入）


@dataclass(frozen=True)
class ModelResult:
    ops: tuple[Op, ...]
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    calls: int
    status: str
    reason: str
    model: str = ""
    # 原始模型条目：add op 需要在编排处按「真实样本仓库 + 代码证据」复核后才能构造（S4）。
    raw_items: tuple[dict[str, Any], ...] = ()


class ModelCaller(Protocol):
    def __call__(self, *, system: str, user: str) -> ModelResult: ...


def _abstract_system() -> str:
    return (
        "你是规律库抽象助手。只返回 JSON 对象，不要 markdown、不要解释。\n"
        '输出 schema：{"items":[{"id":"P-001","chose":"add|strengthen|weaken|refine|falsify|merge",'
        '"alternative":"原因短句","cost":"陈述短句","evidence":"owner/repo|path/file.py:123"}]}\n'
        "★ evidence 必须严格写成 `owner/repo|文件路径:行号`（竖线分隔，行号为正整数），"
        "例如 `vllm-project/vllm|vllm/entrypoints/llm.py:42`。"
        "只写仓库名（如 `vllm-project/vllm`）会被系统判废，条目无法入库。\n"
        "优先从下面给出的「可用代码证据」中挑一条与陈述真正相关的；"
        "没有合适证据就少写。不要写「无法判断/无法验证」。"
    )


def _abstract_user(
    summary: str, projects: Sequence[str], evidence_hints: Sequence[str] = ()
) -> str:
    hints = "\n".join(sorted(set(evidence_hints))[:24])
    return (
        f"## L2 结构化摘要（跨域 run 唯一输入）\n{summary or '（暂无 L2 条目）'}\n\n"
        f"## 本次新增真实项目\n{chr(10).join(sorted(projects))}\n\n"
        f"## 可用代码证据（真实样本的特征卡提取，evidence 必须从这里选或同格式）\n"
        f"{hints or '（暂无可用的 file:line 证据，宁可不写 add）'}"
    )


def _evidence_hints(samples: Sequence[Sample]) -> tuple[str, ...]:
    """从真实样本的特征卡提取 `owner/repo|file:line`，作为模型可引用的证据池。"""
    out: list[str] = []
    for sample in samples:
        for group in ("parallel", "cache"):
            entries = as_dict(as_dict(sample.card.get(group)).get("evidence"))
            for values in entries.values():
                for item in as_list(values):
                    payload = as_dict(item)
                    path = as_str(payload.get("file"))
                    line = as_int(payload.get("line"))
                    if path and line > 0:
                        out.append(f"{sample.repo}|{path}:{line}")
    return tuple(sorted(set(out)))


def _evidence_format_ok(item: dict[str, Any]) -> bool:
    """evidence 必须是 `owner/repo|file:line`，只写仓库名不算。"""
    repo, sep, path = as_str(item.get("evidence")).partition("|")
    tail = path.rsplit(":", 1)[-1]
    return bool(sep and repo and ":" in path and tail.isdigit() and int(tail) > 0)


def _add_op_from_item(
    payload: dict[str, Any], *, allowed_repos: frozenset[str], cluster: str
) -> Op | None:
    """把模型 `add` 条目收敛为**真实样本可核验**的 L1 条目（S4）。

    准入条件：证据写成 ``owner/repo|file:line``；repo 必须是本次真实样本，
    且 path 必须是 file:line。任一条不满足 → 拒绝，模型不能凭空造条目。
    """
    if not cluster:
        return None
    op_id = as_str(payload.get("id"))
    if not op_id:
        return None
    raw_evidence = as_str(payload.get("evidence"))
    repo, sep, path = raw_evidence.partition("|")
    repo, path = repo.strip(), path.strip()
    tail = path.rsplit(":", 1)[-1]
    if not sep or repo not in allowed_repos or ":" not in path or not tail.isdigit():
        return None
    statement = as_str(payload.get("cost")) or as_str(payload.get("alternative"))
    if not statement:
        return None
    entry = PatternEntry(
        id=op_id,
        level="L1",
        cluster=cluster,
        statement=statement,
        evidence=(Evidence(repo=repo, kind="正例", path=path),),
        source="real",
    )
    return Op(op="add", id=op_id, reason=as_str(payload.get("alternative")), entry=entry)


def ops_from_items(
    items: Any, allowed_repos: frozenset[str], *, cluster: str = ""
) -> tuple[Op, ...]:
    """模型输出 → ops：`add` 只有在真实样本 + file:line 证据齐全时才允许（S4）。"""
    result: list[Op] = []
    raw_seq = list(items) if isinstance(items, (list, tuple)) else as_list(items)
    for raw in raw_seq:
        payload = as_dict(raw)
        kind = as_str(payload.get("chose"))
        op_id = as_str(payload.get("id"))
        if kind not in ("add", "strengthen", "weaken", "refine", "falsify", "merge"):
            continue
        if not op_id:
            continue
        if kind == "add":
            add_op = _add_op_from_item(payload, allowed_repos=allowed_repos, cluster=cluster)
            if add_op is not None:
                result.append(add_op)
            continue
        result.append(Op(op=kind, id=op_id, reason=as_str(payload.get("alternative"))))
    return tuple(result)


@dataclass(frozen=True)
class LlmModelCaller:
    """生产用：复用 `llm.LlmClient` 的三级降级阶梯与 usage 回显（不重复造端点）。"""

    config: Config
    max_tokens: int = 4096
    # 证据格式不合规时最多重试一次（计入调用次数与费用，不绕过成本闸门）。
    max_evidence_retries: int = 1

    def __call__(self, *, system: str, user: str) -> ModelResult:
        from .llm import LlmClient  # 局部导入：off 档路径根本不构造模型客户端

        credentials = self.config.llm_credentials()
        if credentials is None:
            return ModelResult(
                ops=(),
                prompt_tokens=0,
                completion_tokens=0,
                cache_hit_tokens=0,
                calls=0,
                status="no_credentials",
                reason="未配置凭据",
            )
        client = LlmClient(
            credentials,
            model=self.config.model_for("fast"),
            thinking=False,
            timeout_seconds=self.config.llm.timeout_seconds,
            max_retries=self.config.llm.max_retries,
        )
        retry_user = user
        total_prompt = total_completion = total_hit = total_calls = 0
        for attempt in range(self.max_evidence_retries + 1):
            outcome = client.chat_json(system, retry_user, max_tokens=self.max_tokens)
            total_prompt += outcome.usage.prompt_tokens
            total_completion += outcome.usage.completion_tokens
            total_hit += outcome.usage.cache_hit_tokens
            total_calls += outcome.calls
            items = outcome.insight.items if outcome.insight else ()
            raw_items = tuple(item.to_json() | {"chose": item.chose} for item in items)
            if outcome.status not in ("ok", "cache_hit") or not raw_items:
                break
            if all(_evidence_format_ok(item) for item in raw_items):
                break
            if attempt == self.max_evidence_retries:
                break
            retry_user = (
                user
                + "\n\n【格式纠正】上一轮 evidence 只写了仓库名，必须为 `owner/repo|路径:行号`"
                + "（行号为正整数）。请重新输出完整 JSON，每条 evidence 都带上真实 file:line。"
            )
        return ModelResult(
            ops=ops_from_items(raw_items, frozenset()),
            raw_items=raw_items,
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            cache_hit_tokens=total_hit,
            calls=total_calls,
            status="ok" if outcome.status in ("ok", "cache_hit") else "degraded",
            reason=outcome.reason,
            model=outcome.model,
        )


class CachedModelCaller:
    """同输入缓存：命中不再调用（T8「不重复调用、同输入缓存」）。"""

    def __init__(self, inner: ModelCaller, layout: Layout) -> None:
        self._inner = inner
        self._layout = layout
        self.hits = 0

    def __call__(self, *, system: str, user: str) -> ModelResult:
        # v2：缓存里同时保存 raw_items（供 add op 按真实样本复核）；旧 key 失效。
        key = sha256_text(f"v2|{system}|{user}")
        path = self._layout.data_dir / "llm_cache" / f"abstract-{key}.json"
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                self.hits += 1
                return ModelResult(
                    ops=tuple(Op.from_json(item) for item in as_list(payload.get("ops"))),
                    prompt_tokens=0,
                    completion_tokens=0,
                    cache_hit_tokens=as_int(payload.get("prompt_tokens")),
                    calls=0,
                    status="cache_hit",
                    reason="同一输入已有结果（结果持久化）",
                    model=as_str(payload.get("model")),
                    raw_items=tuple(as_list(payload.get("raw_items"))),
                )
        result = self._inner(system=system, user=user)
        if result.status == "ok":
            atomic_write_text(
                path,
                stable_json(
                    {
                        "ops": [item.to_json() for item in result.ops],
                        "raw_items": [dict(item) for item in result.raw_items],
                        "prompt_tokens": result.prompt_tokens,
                        "model": result.model,
                    }
                )
                + "\n",
            )
        return result


# --------------------------------------------------------------------------- 编排


@dataclass(frozen=True)
class RunResult:
    record: RunRecord
    entries: tuple[PatternEntry, ...]
    recall_result: RecallResult
    appended: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _last_completed(history: Sequence[RunRecord], cluster: str) -> RunRecord | None:
    matches = [
        item for item in history if item.cluster == cluster and item.status == STATUS_COMPLETED
    ]
    return sorted(matches, key=lambda item: (item.created_at, item.run_id))[-1] if matches else None


def _incremental_runs(history: Sequence[RunRecord], cluster: str) -> int:
    return sum(
        1
        for item in history
        if item.cluster == cluster and item.type == TYPE_CLUSTER and item.status == STATUS_COMPLETED
    )


def cluster_run(
    config: Config,
    *,
    as_of: datetime,
    cluster: str | None = None,
    caller: ModelCaller | None = None,
    off: bool = False,
    write: bool = True,
) -> RunResult:
    """一次抽象 run。所有时间来自 `as_of`；同输入得到同一 run_id → 可重放。"""
    layout = config.layout
    entries = load_library(layout.library_patterns)
    samples, uncovered = load_samples(layout, config)
    history = load_runs(layout)

    counts: dict[str, int] = {}
    for sample in samples:
        if sample.domain is not None:
            counts[sample.domain] = counts.get(sample.domain, 0) + 1
    target = cluster or (sorted(counts, key=lambda key: (-counts[key], key))[0] if counts else "")
    cluster_samples = [sample for sample in samples if sample.domain == target]
    last = _last_completed(history, target)
    known = frozenset(last.input_projects) if last else frozenset()
    new_projects = tuple(sorted({sample.repo for sample in cluster_samples} - known))
    threshold = config.abstract.cluster_min_new_projects
    trigger = f"新增样本 {len(new_projects)} (>= {threshold})"

    projects = tuple(
        ProjectFeatures.from_card(sample.card, sample.domain) for sample in cluster_samples
    )
    recall_result = recall(projects, entries)
    self_check = build_self_check(entries, recall_result.candidates)

    incremental = _incremental_runs(history, target)
    reconcile_due = needs_reconcile(incremental, config.abstract.reconcile_every_incremental_runs)
    run_type = TYPE_RECONCILE if reconcile_due else TYPE_CLUSTER
    input_projects = (
        tuple(sorted(sample.repo for sample in cluster_samples)) if reconcile_due else new_projects
    )
    run_id = run_id_for(run_type=run_type, cluster=target, as_of=as_of, projects=input_projects)

    replay = next((item for item in history if item.run_id == run_id), None)
    if replay is not None:
        return RunResult(
            record=replay,
            entries=entries,
            recall_result=recall_result,
            appended=False,
            warnings=("同一 run_id 已存在 → 重放，未重复调用模型",),
        )

    warnings: list[str] = []
    warnings.extend(f"归类缺口：{repo} 未被 domains 规则覆盖（未自行补规则）" for repo in uncovered)
    warnings.extend(self_check.warnings)
    ops: tuple[Op, ...] = ()
    llm_calls = 0
    status = STATUS_INSUFFICIENT
    produced: tuple[str, ...] = ()
    final_entries = entries

    if len(new_projects) < threshold:
        warnings.append(
            f"首次真实抽象未触发，原因：样本 {len(new_projects)} < {threshold}（S1 / S4）"
        )
        warnings.append("本轮产 0 条、0 次 LLM；仅验证门槛 / ops / 反例 / reconcile 链路")
    else:
        summary = l2_summary(entries)
        estimated = estimate_tokens(_abstract_user(summary, input_projects))
        allowed, gate_reason = budget_gate(config, as_of=as_of, estimated_prompt_tokens=estimated)
        if not allowed:
            status = STATUS_BUDGET_BLOCKED
            warnings.append(f"预算闸门拦截：{gate_reason}")
            if write:
                record_event(
                    layout,
                    _cost_event(
                        event=EVENT_BLOCKED,
                        run_id=run_id,
                        as_of=as_of,
                        model="",
                        prompt_tokens=0,
                        completion_tokens=0,
                        cache_hit_tokens=0,
                        reason=f"budget_blocked: {gate_reason}",
                        purpose=run_type,
                        estimated_cost=None,
                    ),
                )
        elif off or caller is None:
            status = STATUS_NO_CREDENTIALS
            warnings.append("off 档 / 无凭据 → 零 LLM，抽象 run 未发起调用")
            if write:
                record_event(
                    layout,
                    _cost_event(
                        event=EVENT_DOWNGRADE,
                        run_id=run_id,
                        as_of=as_of,
                        model="",
                        prompt_tokens=0,
                        completion_tokens=0,
                        cache_hit_tokens=0,
                        reason="off / no_credentials",
                        purpose=run_type,
                        estimated_cost=None,
                    ),
                )
        else:
            hints = _evidence_hints(samples)
            result = caller(
                system=_abstract_system(),
                user=_abstract_user(summary, input_projects, hints),
            )
            llm_calls = result.calls
            # S4：模型原始 add 条目必须按本次真实样本 + file:line 证据复核后才能成为 op。
            existing_ids = {entry.id for entry in entries}
            add_ops = ops_from_items(result.raw_items, frozenset(input_projects), cluster=target)
            seen_ids: set[str] = set()
            validated_adds: list[Op] = []
            for item in add_ops:
                if item.id in existing_ids or item.id in seen_ids:
                    continue
                seen_ids.add(item.id)
                validated_adds.append(item)
            ops = result.ops + tuple(validated_adds)
            model = result.model or config.model_for("fast")
            cost = estimate_cost(
                config,
                model=model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cache_hit_tokens=result.cache_hit_tokens,
            )
            if write:
                record_event(
                    layout,
                    _cost_event(
                        event=EVENT_CACHE_HIT if result.status == "cache_hit" else EVENT_CALL,
                        run_id=run_id,
                        as_of=as_of,
                        model=model,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        cache_hit_tokens=result.cache_hit_tokens,
                        reason=result.reason or result.status,
                        purpose=run_type,
                        estimated_cost=cost,
                    ),
                )
            if result.status in ("ok", "cache_hit") and ops:
                final_entries, op_warnings = apply_ops(entries, ops)
                warnings.extend(op_warnings)
                try:
                    assert_storable(final_entries)
                except PatternError as exc:
                    warnings.append(f"ops 产物被拒（真源未写）：{exc}")
                    final_entries, ops, status = entries, (), STATUS_DEGRADED
                else:
                    produced = tuple(
                        sorted(
                            {op.id for op in ops if op.op == "add"}
                            | {entry.id for entry in final_entries if entry.revision > 1}
                        )
                    )
                    status = STATUS_COMPLETED
                    if write:
                        save_library(layout.library_patterns, final_entries)
                        append_ops(layout.ops_jsonl, run_id, ops)
            else:
                status = STATUS_DEGRADED
                if result.status in ("ok", "cache_hit") and not ops:
                    warnings.append("模型输出无可用 ops：add 条目未带「真实样本 + file:line」证据")
                else:
                    reason = result.reason or "无"
                    warnings.append(f"模型输出判废/不可用：status={result.status} reason={reason}")

    record = RunRecord(
        run_id=run_id,
        type=run_type,
        cluster=target,
        trigger=trigger,
        input_projects=input_projects,
        input_patterns=tuple(sorted(entry.id for entry in entries)),
        ops=ops,
        llm_calls=llm_calls,
        created_at=fmt_iso(as_of),
        status=status,
        self_check=self_check,
        warnings=tuple(warnings),
        produced_patterns=produced,
    )
    appended = append_run(layout, record) if write else False
    return RunResult(
        record=record,
        entries=final_entries,
        recall_result=recall_result,
        appended=appended,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- 跨域抽象（Q5 / T2）


def _completed_cluster_runs(history: Sequence[RunRecord]) -> int:
    """已完成的簇内增量 run 数（不含 reconcile / 跨域 / 未达阈值）。"""
    return sum(
        1 for item in history if item.type == TYPE_CLUSTER and item.status == STATUS_COMPLETED
    )


def cross_domain_run(
    config: Config,
    *,
    as_of: datetime,
    caller: ModelCaller | None = None,
    off: bool = False,
    write: bool = True,
) -> RunResult:
    """跨域抽象 run（L3）。**独立入口，不与簇内 run 混排**（`--cross` 显式调用）。

    ★ 触发判定消费 `cross_domain_min_l2_entries`（8）与 `cross_domain_every_cluster_runs`（4），
      经 `should_cross_domain` 汇总（helper 由此进入生产调用链，不再只被单测调用）。
    ★ 输入 = L2 **结构化摘要**（`l2_summary`），不重喂全量项目；无真实 L2 条目时
      `insufficient_samples` 合法终态、产 0 条、0 次 LLM（真源纯净，不伪造条目凑数）。
    ★ `budget_gate`（`estimate_safety_factor`）与 `off` 零 LLM 与簇内路径一致；
      `CachedModelCaller` 由调用方注入，命中不重复调用。
    ★ 所有时间来自 `as_of`；同输入派生同一 run_id → 可重放。
    """
    layout = config.layout
    entries = load_library(layout.library_patterns)
    history = load_runs(layout)

    l2_entries = [e for e in entries if e.level == "L2" and e.status != "falsified"]
    cluster_runs = _completed_cluster_runs(history)
    min_entries = config.abstract.cross_domain_min_l2_entries
    every_runs = config.abstract.cross_domain_every_cluster_runs
    triggered = should_cross_domain(
        len(l2_entries), cluster_runs, min_entries=min_entries, every_runs=every_runs
    )

    input_patterns = tuple(sorted(e.id for e in l2_entries))
    input_projects: tuple[str, ...] = ()  # 跨域 run 不重喂全量项目
    summary = l2_summary(entries)
    trigger = (
        f"L2 条目 {len(l2_entries)} (>= {min_entries}) / 簇内 run {cluster_runs} (每 {every_runs})"
    )
    run_id = run_id_for(
        run_type=TYPE_CROSS_DOMAIN,
        cluster=CROSS_DOMAIN_CLUSTER,
        as_of=as_of,
        projects=input_patterns,
    )

    replay = next((item for item in history if item.run_id == run_id), None)
    if replay is not None:
        return RunResult(
            record=replay,
            entries=entries,
            recall_result=RecallResult(rows=(), candidates=()),
            appended=False,
            warnings=("同一 run_id 已存在 → 重放，未重复调用模型",),
        )

    recall_result = RecallResult(rows=(), candidates=())
    self_check = build_self_check(entries, recall_result.candidates)

    warnings: list[str] = []
    warnings.extend(self_check.warnings)
    ops: tuple[Op, ...] = ()
    llm_calls = 0
    status = STATUS_INSUFFICIENT
    produced: tuple[str, ...] = ()
    final_entries = entries

    if not l2_entries:
        warnings.append("无真实 L2 条目 → 跨域抽象未触发（真源纯净，不伪造条目凑数）")
        warnings.append("本轮产 0 条、0 次 LLM；跨域阈值与闸门链路仍已验证")
    elif not triggered:
        warnings.append(f"跨域阈值未达：{trigger}")
        warnings.append("本轮产 0 条、0 次 LLM；未达阈值属合法终态")
    else:
        estimated = estimate_tokens(_abstract_user(summary, input_projects))
        allowed, gate_reason = budget_gate(config, as_of=as_of, estimated_prompt_tokens=estimated)
        if not allowed:
            status = STATUS_BUDGET_BLOCKED
            warnings.append(f"预算闸门拦截：{gate_reason}")
            if write:
                record_event(
                    layout,
                    _cost_event(
                        event=EVENT_BLOCKED,
                        run_id=run_id,
                        as_of=as_of,
                        model="",
                        prompt_tokens=0,
                        completion_tokens=0,
                        cache_hit_tokens=0,
                        reason=f"budget_blocked: {gate_reason}",
                        purpose=TYPE_CROSS_DOMAIN,
                        estimated_cost=None,
                    ),
                )
        elif off or caller is None:
            status = STATUS_NO_CREDENTIALS
            warnings.append("off 档 / 无凭据 → 零 LLM，跨域 run 未发起调用")
            if write:
                record_event(
                    layout,
                    _cost_event(
                        event=EVENT_DOWNGRADE,
                        run_id=run_id,
                        as_of=as_of,
                        model="",
                        prompt_tokens=0,
                        completion_tokens=0,
                        cache_hit_tokens=0,
                        reason="off / no_credentials",
                        purpose=TYPE_CROSS_DOMAIN,
                        estimated_cost=None,
                    ),
                )
        else:
            result = caller(system=_abstract_system(), user=_abstract_user(summary, input_projects))
            llm_calls = result.calls
            existing_ids = {entry.id for entry in entries}
            add_ops = ops_from_items(
                result.raw_items, frozenset(input_projects), cluster=CROSS_DOMAIN_CLUSTER
            )
            seen_ids: set[str] = set()
            validated_adds: list[Op] = []
            for item in add_ops:
                if item.id in existing_ids or item.id in seen_ids:
                    continue
                seen_ids.add(item.id)
                validated_adds.append(item)
            ops = result.ops + tuple(validated_adds)
            model = result.model or config.model_for("fast")
            cost = estimate_cost(
                config,
                model=model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cache_hit_tokens=result.cache_hit_tokens,
            )
            if write:
                record_event(
                    layout,
                    _cost_event(
                        event=EVENT_CACHE_HIT if result.status == "cache_hit" else EVENT_CALL,
                        run_id=run_id,
                        as_of=as_of,
                        model=model,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        cache_hit_tokens=result.cache_hit_tokens,
                        reason=result.reason or result.status,
                        purpose=TYPE_CROSS_DOMAIN,
                        estimated_cost=cost,
                    ),
                )
            if result.status in ("ok", "cache_hit") and ops:
                final_entries, op_warnings = apply_ops(entries, ops)
                warnings.extend(op_warnings)
                try:
                    assert_storable(final_entries)
                except PatternError as exc:
                    warnings.append(f"ops 产物被拒（真源未写）：{exc}")
                    final_entries, ops, status = entries, (), STATUS_DEGRADED
                else:
                    produced = tuple(sorted({op.id for op in ops if op.op == "add"}))
                    status = STATUS_COMPLETED
                    if write:
                        save_library(layout.library_patterns, final_entries)
                        append_ops(layout.ops_jsonl, run_id, ops)
            else:
                status = STATUS_DEGRADED
                if result.status in ("ok", "cache_hit") and not ops:
                    warnings.append("模型输出无可用 ops：add 条目未带「真实样本 + file:line」证据")
                else:
                    reason = result.reason or "无"
                    warnings.append(f"模型输出判废/不可用：status={result.status} reason={reason}")

    record = RunRecord(
        run_id=run_id,
        type=TYPE_CROSS_DOMAIN,
        cluster=CROSS_DOMAIN_CLUSTER,
        trigger=trigger,
        input_projects=input_projects,
        input_patterns=input_patterns,
        ops=ops,
        llm_calls=llm_calls,
        created_at=fmt_iso(as_of),
        status=status,
        self_check=self_check,
        warnings=tuple(warnings),
        produced_patterns=produced,
    )
    appended = append_run(layout, record) if write else False
    return RunResult(
        record=record,
        entries=final_entries,
        recall_result=recall_result,
        appended=appended,
        warnings=tuple(warnings),
    )
