"""档位四层 + 预算闸门 + Ledger（设计方案 §2 / §9 / §11）。

四层：
  L1 通道基线 → L2 周配额 → L3 预算闸门 → L4 人工 override
★ 降级必须双写：报告「运行元数据」块 + `costs.jsonl`（红线 #10）。
★ L4 可绕过 L1/L2，**不能绕过 L3**。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from .config import Config, Layout
from .util import (
    UsageError,
    append_jsonl,
    as_float,
    as_int,
    as_str,
    fmt_iso,
    parse_iso,
    r4,
    read_jsonl,
    sha256_text,
    start_of_month,
    start_of_week,
)

DEPTHS = ("off", "fast", "strong")
# 档位成本序（off < fast < strong）：供自动链把通道基线收敛到 auto_default 上限。
_DEPTH_RANK = {name: index for index, name in enumerate(DEPTHS)}
REQUESTED_DEPTHS = ("auto", "off", "fast", "strong")

EVENT_CALL = "call"
EVENT_DOWNGRADE = "downgrade"
EVENT_BLOCKED = "blocked"
EVENT_CACHE_HIT = "cache_hit"
EVENT_KINDS = (EVENT_CALL, EVENT_DOWNGRADE, EVENT_BLOCKED, EVENT_CACHE_HIT)

# 路径 B / C1.4：自动链编排 run 归因。workflow 注入 OSSLENS_AUTO_RUN_ID（= github.run_id），
# record_event 把该值关联到本次编排产生的每一笔 costs.jsonl 行；手动 / 本地不设该环境变量
# → 字段恒空、to_json 不新增任何 key → 既有台账字节 / 幂等 / 报告契约零影响。
AUTO_RUN_ID_ENV = "OSSLENS_AUTO_RUN_ID"
ORCHESTRATION_FIELD = "orchestration_run"


def orchestration_run_from_env(environ: Mapping[str, str] | None = None) -> str:
    """读取自动链编排 run id；未注入返回空串。environ 可注入便于单测，默认读进程环境。"""
    source = os.environ if environ is None else environ
    return as_str(source.get(AUTO_RUN_ID_ENV))


REASON_TEXT = {
    "explicit_off": "显式请求 off 档（零 LLM）",
    "no_credentials": "未配置 LLM 凭据（api_key / base_url / model 缺一）",
    "weekly_quota_exhausted": "本周配额已用满",
    "budget_blocked": "预算闸门拦截",
    "depth_unavailable_in_l0": "L0 尚未接入 LLM 档位（L1 起启用）",
    "depth_unavailable_in_l1": "该档位尚未接入（L1 只实跑 fast）",
    "manual_override": "人工 override",
    "baseline": "按通道基线",
    "auto_default_off": "自动链默认档位为 off（零 LLM）",
}


@dataclass(frozen=True)
class CostEvent:
    event: str
    repo: str
    depth: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float | None
    source: str
    as_of: str
    run_id: str
    requested_depth: str
    actual_depth: str
    reason: str
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    purpose: str = ""
    reasoning_tokens: int = 0
    # 路径 B / C1.4：自动链编排 run 归因（空 = 手动 / 本地，to_json 不写出该 key）。
    orchestration_run: str = ""

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "actual_depth": self.actual_depth,
            "as_of": self.as_of,
            "completion_tokens": self.completion_tokens,
            "cache_hit_tokens": self.cache_hit_tokens,
            "cache_miss_tokens": self.cache_miss_tokens,
            "purpose": self.purpose,
            "reasoning_tokens": self.reasoning_tokens,
            "depth": self.depth,
            "estimated_cost": self.estimated_cost,
            "event": self.event,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "reason": self.reason,
            "repo": self.repo,
            "requested_depth": self.requested_depth,
            "run_id": self.run_id,
            "source": self.source,
        }
        # 只在自动链注入时才多一个 key：手动 / 本地字节与既有完全一致（幂等零影响）。
        if self.orchestration_run:
            payload[ORCHESTRATION_FIELD] = self.orchestration_run
        return payload

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> CostEvent:
        cost = value.get("estimated_cost")
        return cls(
            event=as_str(value.get("event"), EVENT_CALL),
            repo=as_str(value.get("repo")),
            depth=as_str(value.get("depth"), "off"),
            model=as_str(value.get("model")),
            prompt_tokens=as_int(value.get("prompt_tokens")),
            completion_tokens=as_int(value.get("completion_tokens")),
            estimated_cost=as_float(cost) if isinstance(cost, (int, float)) else None,
            source=as_str(value.get("source"), "skipped"),
            as_of=as_str(value.get("as_of")),
            run_id=as_str(value.get("run_id")),
            requested_depth=as_str(value.get("requested_depth"), "auto"),
            actual_depth=as_str(value.get("actual_depth")),
            reason=as_str(value.get("reason")),
            cache_hit_tokens=as_int(value.get("cache_hit_tokens")),
            cache_miss_tokens=as_int(value.get("cache_miss_tokens")),
            purpose=as_str(value.get("purpose")),
            reasoning_tokens=as_int(value.get("reasoning_tokens")),
            orchestration_run=as_str(value.get(ORCHESTRATION_FIELD)),
        )


@dataclass(frozen=True)
class QuotaState:
    week_start: str
    month_start: str
    strong_used: int
    strong_limit: int
    fast_used: int
    fast_limit: int
    tokens_week: int
    tokens_week_limit: int
    tokens_month: int
    tokens_month_limit: int

    def used(self, depth: str) -> int:
        return self.strong_used if depth == "strong" else self.fast_used

    def limit(self, depth: str) -> int:
        return self.strong_limit if depth == "strong" else self.fast_limit

    def exhausted(self, depth: str) -> bool:
        return self.used(depth) >= self.limit(depth)

    def summary(self) -> str:
        return (
            f"strong {self.strong_used}/{self.strong_limit}、"
            f"fast {self.fast_used}/{self.fast_limit}"
            f"（周起点 {self.week_start}）；"
            f"tokens 周 {self.tokens_week}/{self.tokens_week_limit}、"
            f"月 {self.tokens_month}/{self.tokens_month_limit}（月起点 {self.month_start}）"
        )


@dataclass(frozen=True)
class DepthDecision:
    requested: str
    actual: str
    reason: str
    downgraded: bool
    chain: tuple[str, ...]
    quota: QuotaState
    credentials_present: bool
    estimated_prompt_tokens: int
    prompt_token_limit: int

    @property
    def reason_text(self) -> str:
        return REASON_TEXT.get(self.reason, self.reason)


@dataclass(frozen=True)
class CostSummary:
    as_of: str
    week_start: str
    month_start: str
    week_tokens: int
    month_tokens: int
    week_cost: float
    month_cost: float
    cost_complete: bool
    week_downgrades: int
    month_downgrades: int
    week_blocked: int
    month_blocked: int
    by_depth: dict[str, int]
    by_purpose: dict[str, dict[str, int]]
    week_cache_hit_tokens: int
    month_cache_hit_tokens: int
    budget_week_remaining: int
    budget_month_remaining: int
    anomalies: tuple[str, ...]


def last_auto_call_at(events: Sequence[CostEvent]) -> datetime | None:
    """最近一次「自动链真实分析」时间：`event=call` 且带编排归因字段。

    ★ 只认自动链（`orchestration_run` 非空）：降级 / blocked / 本地手动调用都不算真实分析。
    ★ 解析失败的行跳过（台账允许历史字段缺失，不因单行脏数据阻断闸门）。
    """
    latest: datetime | None = None
    for event in events:
        if event.event != EVENT_CALL or not event.orchestration_run:
            continue
        try:
            moment = parse_iso(event.as_of)
        except ValueError:
            continue
        if latest is None or moment > latest:
            latest = moment
    return latest


def auto_interval_reached(
    config: Config,
    events: Sequence[CostEvent],
    *,
    now: datetime,
) -> bool:
    """路径 B：`schedule` 的「自动真实分析最小间隔」闸门。

    - 无历史自动真实分析 → True（首次放行）。
    - 距最近一次自动真实分析满 `auto_chain.min_interval_days` 天 → True。
    - 未满 → False；调用方必须在 `first_auto_slug` / `analyze` / 真源回写 / 站点重建**之前**退出。
    - `workflow_dispatch` 不由本函数区分：调用方只对 `schedule` 使用本结果
      （手动绕过间隔、不绕过成本闸门）。
    """
    last = last_auto_call_at(events)
    if last is None:
        return True
    return now - last >= timedelta(days=config.auto_chain.min_interval_days)


def load_events(layout: Layout) -> list[CostEvent]:
    events = []
    for record in read_jsonl(layout.costs_jsonl):
        if as_str(record.get("event")) in EVENT_KINDS:
            events.append(CostEvent.from_json(record))
    return events


def run_id_for(repo: str, as_of: str, requested: str, actual: str, reason: str) -> str:
    """确定性 run_id：不引入运行时钟，重跑可复现。"""
    return sha256_text(f"{repo}|{as_of}|{requested}|{actual}|{reason}")[:16]


def compute_quota(config: Config, events: Sequence[CostEvent], as_of: datetime) -> QuotaState:
    week_start = start_of_week(as_of)
    month_start = start_of_month(as_of)
    strong_used = fast_used = 0
    week_tokens = month_tokens = 0
    for event in events:
        if event.event != EVENT_CALL:
            continue
        try:
            when = parse_iso(event.as_of)
        except ValueError:
            continue
        tokens = event.prompt_tokens + event.completion_tokens
        if when >= month_start:
            month_tokens += tokens
        if when >= week_start:
            week_tokens += tokens
            if event.depth == "strong":
                strong_used += 1
            elif event.depth == "fast":
                fast_used += 1
    return QuotaState(
        week_start=week_start.strftime("%Y-%m-%d"),
        month_start=month_start.strftime("%Y-%m-%d"),
        strong_used=strong_used,
        strong_limit=config.depth.weekly_quota.get("strong", 0),
        fast_used=fast_used,
        fast_limit=config.depth.weekly_quota.get("fast", 0),
        tokens_week=week_tokens,
        tokens_week_limit=config.depth.budget.weekly_tokens,
        tokens_month=month_tokens,
        tokens_month_limit=config.depth.budget.monthly_tokens,
    )


def _cap_by_auto_default(channel_baseline: str, auto_default: str) -> str:
    """自动链最终基线 = 通道基线与 auto_default 中**成本更低者**。

    ★ 通道基线仍被评估（受通道基线约束），自动链只取更省的一档，绝不因 auto_default 抬高。
    """
    base_rank = _DEPTH_RANK.get(channel_baseline, len(DEPTHS))
    auto_rank = _DEPTH_RANK.get(auto_default, len(DEPTHS))
    return channel_baseline if base_rank <= auto_rank else auto_default


def resolve_depth(
    config: Config,
    *,
    requested: str,
    channel: str,
    as_of: datetime,
    events: Sequence[CostEvent],
    available_depths: frozenset[str] = frozenset(),
    estimated_prompt_tokens: int = 0,
    credentials_present: bool | None = None,
    unavailable_reason: str = "depth_unavailable_in_l0",
    auto_chain: bool = False,
) -> DepthDecision:
    """四层档位决策。``auto_chain=True`` 时**绝不进入 L4 人工 override**：

    自动链默认档位取 ``depth.auto_default``（fast），但 L1 通道基线、L2 周次数配额、
    L3 预算（单次 / 周 / 月 token × 安全系数）照常全链生效——同一 fast 值走「基线闸门」
    而非「人工显式指定档位」，因此不会被 `_cap_by_auto_default` 之外的任何层绕过。
    """
    if requested not in REQUESTED_DEPTHS:
        raise UsageError(f"--depth 只能是 {', '.join(REQUESTED_DEPTHS)}，实际为 {requested!r}")

    quota = compute_quota(config, events, as_of)
    present = (
        credentials_present
        if credentials_present is not None
        else config.llm_credentials() is not None
    )
    per_run_limit = config.depth.budget.per_run_prompt_tokens
    chain: list[str] = []

    def decide(actual: str, reason: str, downgraded: bool) -> DepthDecision:
        return DepthDecision(
            requested=requested,
            actual=actual,
            reason=reason,
            downgraded=downgraded,
            chain=tuple(chain),
            quota=quota,
            credentials_present=present,
            estimated_prompt_tokens=estimated_prompt_tokens,
            prompt_token_limit=per_run_limit,
        )

    if requested == "off":
        if auto_chain:
            chain.append("自动链默认档位 auto_default=off（零 LLM；非人工 override）")
            return decide("off", "auto_default_off", False)
        chain.append("L4 人工 override：显式 --depth off（不再评估其它层）")
        return decide("off", "explicit_off", False)

    # ★ 自动链：requested 仅为 auto_default（如 fast），绝不视为「人工显式指定档位」。
    #   manual 强制 False → 不进入 L4 override；L1 通道基线照常评估，再按 auto_default 取
    #   成本更低者；L2 周配额 / L3 预算 / 能力 / 凭据全链照常生效（见后续分支）。
    manual = requested in ("fast", "strong") and not auto_chain
    if auto_chain:
        channel_baseline = config.depth.baseline.get(channel, "fast")
        baseline = _cap_by_auto_default(channel_baseline, config.depth.auto_default)
        if baseline != channel_baseline:
            chain.append(
                f"L1 通道基线：{channel} → {channel_baseline}；"
                f"自动链按 auto_default={config.depth.auto_default} 取更省档位 → {baseline}"
                "（非 L4 人工 override）"
            )
        else:
            chain.append(
                f"L1 通道基线：{channel} → {baseline}"
                f"（自动链默认档位 auto_default={config.depth.auto_default}，非 L4 人工 override）"
            )
    elif manual:
        baseline = requested
        chain.append(f"L4 人工 override：--depth {requested}（绕过 L1 基线 / L2 配额）")
    else:
        baseline = config.depth.baseline.get(channel, "fast")
        chain.append(f"L1 通道基线：{channel} → {baseline}")

    if not present:
        chain.append("凭据：api_key / base_url / model 缺一 → 降级 off（退出码仍为 0）")
        return decide("off", "no_credentials", True)
    chain.append("凭据：齐全")

    # 能力检查先于预算：L0 根本没有 LLM 实现，谈配额/预算没有意义
    if baseline != "off" and baseline not in available_depths:
        chain.append(f"实现能力：{baseline} 尚未接入 → 降级 off")
        return decide("off", unavailable_reason, True)

    depth = baseline
    if manual:
        chain.append(
            f"L2 周配额：人工 override 绕过（本周 strong {quota.strong_used}/{quota.strong_limit}、"
            f"fast {quota.fast_used}/{quota.fast_limit}）"
        )
    else:
        while depth != "off" and quota.exhausted(depth):
            chain.append(f"L2 周配额：{depth} 已用 {quota.used(depth)}/{quota.limit(depth)} → 降级")
            depth = "fast" if depth == "strong" else "off"
        if depth != baseline:
            return decide(depth, "weekly_quota_exhausted", True)
        chain.append(f"L2 周配额：{depth} 已用 {quota.used(depth)}/{quota.limit(depth)}，未用满")

    gate_estimate = config.safety_adjusted(estimated_prompt_tokens)
    factor = config.depth.budget.estimate_safety_factor
    over_budget = (
        gate_estimate > per_run_limit
        or quota.tokens_week + gate_estimate > quota.tokens_week_limit
        or quota.tokens_month + gate_estimate > quota.tokens_month_limit
    )
    estimate_note = (
        f"估算 {estimated_prompt_tokens} × 安全系数 {factor:g} = {gate_estimate} tok"
        if gate_estimate != estimated_prompt_tokens
        else f"估算 {estimated_prompt_tokens} tok（安全系数 {factor:g}）"
    )
    if over_budget:
        chain.append(
            f"L3 预算：{estimate_note}、"
            f"周 {quota.tokens_week}/{quota.tokens_week_limit}、"
            f"月 {quota.tokens_month}/{quota.tokens_month_limit} → 拦截（L4 也不能绕过）"
        )
        return decide("off", "budget_blocked", True)
    chain.append(
        f"L3 预算：{estimate_note}（单选上限 {per_run_limit}），"
        f"周 {quota.tokens_week}/{quota.tokens_week_limit}"
    )

    reason = "manual_override" if manual else "baseline"
    chain.append(f"结论：实际档位 {depth}（{REASON_TEXT[reason]}）")
    return decide(depth, reason, False)


def build_ledger_event(
    *,
    repo: str,
    as_of: datetime,
    decision: DepthDecision,
    model: str = "",
) -> CostEvent:
    """降级 / 预算拦截的留痕事件。**只在 decision.downgraded 时调用。**"""
    as_of_iso = fmt_iso(as_of)
    kind = EVENT_BLOCKED if decision.reason == "budget_blocked" else EVENT_DOWNGRADE
    return CostEvent(
        event=kind,
        repo=repo,
        depth=decision.actual,
        model=model,
        prompt_tokens=0,
        completion_tokens=0,
        estimated_cost=None,
        source="skipped",
        as_of=as_of_iso,
        run_id=run_id_for(repo, as_of_iso, decision.requested, decision.actual, decision.reason),
        requested_depth=decision.requested,
        actual_depth=decision.actual,
        reason=decision.reason,
    )


def record_event(layout: Layout, event: CostEvent) -> bool:
    """追加台账；**同一条记录已存在则跳过**（重跑不产生重复计数，仍保持 append-only）。

    返回是否真的追加了。
    路径 B / C1.4：自动链编排 run 注入 OSSLENS_AUTO_RUN_ID 时，把它关联到本次写出的
    每一笔台账行；手动 / 本地无该环境变量 → 不注入，event 保持原样（零影响）。
    """
    if not event.orchestration_run:
        run = orchestration_run_from_env()
        if run:
            event = replace(event, orchestration_run=run)
    payload = event.to_json()
    existing = read_jsonl(layout.costs_jsonl)
    if any(record == payload for record in existing):
        return False
    append_jsonl(layout.costs_jsonl, payload)
    return True


def estimate_cost(
    config: Config,
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_hit_tokens: int = 0,
) -> float | None:
    """单价表为空 → 返回 None（渲染为 `—`），绝不内置价格。

    缓存命中的输入按 `cache_hit_per_1m` 计价，其余按 `prompt_per_1m`（红线 M6）。
    """
    entry = config.llm.price_table.get(model)
    if entry is None:
        return None
    hit = min(max(cache_hit_tokens, 0), max(prompt_tokens, 0))
    miss = max(prompt_tokens - hit, 0)
    cost = (
        hit / 1_000_000 * entry.cache_hit_per_1m
        + miss / 1_000_000 * entry.prompt_per_1m
        + completion_tokens / 1_000_000 * entry.completion_per_1m
    )
    return r4(cost)


def summarize(config: Config, events: Sequence[CostEvent], *, as_of: datetime) -> CostSummary:
    week_start = start_of_week(as_of)
    month_start = start_of_month(as_of)
    week_tokens = month_tokens = 0
    week_cost = month_cost = 0.0
    cost_complete = True
    week_downgrades = month_downgrades = 0
    week_blocked = month_blocked = 0
    by_depth: dict[str, int] = {}
    by_purpose: dict[str, dict[str, int]] = {}
    week_cache_hit = 0
    month_cache_hit = 0
    # 同一 run_id 只算一次：修复前遗留的重复行不得让"降级次数"虚高（读取侧去重，不动台账）
    seen_downgrades: set[str] = set()
    seen_blocked: set[str] = set()
    for event in events:
        try:
            when = parse_iso(event.as_of)
        except ValueError:
            continue
        in_week = when >= week_start
        in_month = when >= month_start
        key = event.run_id or f"{event.repo}|{event.as_of}|{event.reason}"
        if event.event == EVENT_DOWNGRADE:
            if key in seen_downgrades:
                continue
            seen_downgrades.add(key)
            week_downgrades += 1 if in_week else 0
            month_downgrades += 1 if in_month else 0
            continue
        if event.event == EVENT_BLOCKED:
            if key in seen_blocked:
                continue
            seen_blocked.add(key)
            week_blocked += 1 if in_week else 0
            month_blocked += 1 if in_month else 0
            continue
        if event.event != EVENT_CALL:
            continue
        tokens = event.prompt_tokens + event.completion_tokens
        if in_week:
            week_tokens += tokens
            week_cache_hit += event.cache_hit_tokens
            by_depth[event.depth] = by_depth.get(event.depth, 0) + 1
            purpose = event.purpose or "unspecified"
            bucket = by_purpose.setdefault(purpose, {"calls": 0, "tokens": 0})
            bucket["calls"] += 1
            bucket["tokens"] += tokens
        if in_month:
            month_tokens += tokens
            month_cache_hit += event.cache_hit_tokens
        cost = event.estimated_cost
        if cost is None:
            if tokens:
                cost_complete = False
        else:
            if in_week:
                week_cost += cost
            if in_month:
                month_cost += cost
    return CostSummary(
        as_of=fmt_iso(as_of),
        week_start=week_start.strftime("%Y-%m-%d"),
        month_start=month_start.strftime("%Y-%m-%d"),
        week_tokens=week_tokens,
        month_tokens=month_tokens,
        week_cost=r4(week_cost),
        month_cost=r4(month_cost),
        cost_complete=cost_complete,
        week_downgrades=week_downgrades,
        month_downgrades=month_downgrades,
        week_blocked=week_blocked,
        month_blocked=month_blocked,
        by_depth=dict(sorted(by_depth.items())),
        by_purpose={key: dict(sorted(value.items())) for key, value in sorted(by_purpose.items())},
        week_cache_hit_tokens=week_cache_hit,
        month_cache_hit_tokens=month_cache_hit,
        budget_week_remaining=max(0, config.depth.budget.weekly_tokens - week_tokens),
        budget_month_remaining=max(0, config.depth.budget.monthly_tokens - month_tokens),
        anomalies=(),
    )
