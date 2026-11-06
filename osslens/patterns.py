"""L3 规律库：零 LLM 三态召回 / 四层条目 schema / 增量 merge / 反例挖掘 / 自检四问。

依据：设计方案 v1.4 §4 / §7、规律库与范围配置 v0.2 §B–§G、执行手册 附录 B、L3 卡 T3–T7。

★ 本模块完全确定性、零 LLM：不构造任何 HTTP 客户端、不含模型端点字面量、
  不读运行时钟。所有集合输出前排序，浮点 r4，JSON sort_keys。
★ 真源纯净（S4）：`source=synthetic` 的条目禁止写入 `patterns/*.yaml`；fixture 只进 tests/。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import yaml

from .util import (
    OsslensError,
    append_jsonl,
    as_bool,
    as_dict,
    as_int,
    as_list,
    as_str,
    atomic_write_text,
    r4,
)

LEVELS = ("L1", "L2", "L3", "L4")
STATUSES = ("active", "weakened", "falsified")
SOURCES = ("real", "synthetic")
OPS = ("add", "strengthen", "weaken", "refine", "falsify", "merge")

STATE_MATCHED = "matched"
STATE_NEW_CANDIDATE = "new_candidate"
STATE_NOT_APPLICABLE = "not_applicable"
RECALL_STATES = (STATE_MATCHED, STATE_NEW_CANDIDATE, STATE_NOT_APPLICABLE)
STATE_LABELS = {
    STATE_MATCHED: "已命中",
    STATE_NEW_CANDIDATE: "新模式候选",
    STATE_NOT_APPLICABLE: "不适用",
}

# 软标签：特征卡派生的结构标签，多值，用于跨域召回（规律库 §C）。
SOFT_LABEL_PREFIXES = (
    ("cache.hits", "cache-reuse"),
    ("parallel.hits", "sharding"),
    ("hardware.kernel_langs", "kernel-fusion"),
    ("hardware.vendors", "hardware-lock-in"),
)


class PatternError(OsslensError):
    """条目/ops 违反规格 → 拒绝入库（不是降级，也不产出半截真源）。"""


# --------------------------------------------------------------------------- 数据结构


@dataclass(frozen=True)
class Evidence:
    repo: str
    kind: str  # 正例 | 反例
    path: str = ""  # file:line（L1 代码证据）
    commit: str = ""
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "kind": self.kind,
            "path": self.path,
            "commit": self.commit,
            "note": self.note,
        }

    @classmethod
    def from_json(cls, value: Any) -> Evidence:
        payload = as_dict(value)
        return cls(
            repo=as_str(payload.get("repo")),
            kind=as_str(payload.get("kind")),
            path=as_str(payload.get("path")),
            commit=as_str(payload.get("commit")),
            note=as_str(payload.get("note")),
        )


@dataclass(frozen=True)
class PatternEntry:
    """规律库条目（执行手册 附录 B + 规律库 §F）。"""

    id: str
    level: str
    cluster: str
    statement: str
    tags: tuple[str, ...] = ()
    applicability: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    counterexamples: tuple[Evidence, ...] = ()
    confidence: str = "中"
    falsification: str = ""
    revision: int = 1
    status: str = "active"
    cross_domains: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()
    anti_patterns: tuple[str, ...] = ()
    drilldown: tuple[str, ...] = ()
    control_group: tuple[str, ...] = ()
    claim_kind: str = ""
    source: str = "real"
    aliases: tuple[str, ...] = ()
    soft_labels: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level,
            "cluster": self.cluster,
            "statement": self.statement,
            "tags": sorted(self.tags),
            "applicability": sorted(self.applicability),
            "evidence": [item.to_json() for item in self.evidence],
            "counterexamples": [item.to_json() for item in self.counterexamples],
            "confidence": self.confidence,
            "falsification": self.falsification,
            "revision": self.revision,
            "status": self.status,
            "cross_domains": sorted(self.cross_domains),
            "boundaries": sorted(self.boundaries),
            "anti_patterns": sorted(self.anti_patterns),
            "drilldown": list(self.drilldown),
            "control_group": sorted(self.control_group),
            "claim_kind": self.claim_kind,
            "source": self.source,
            "aliases": sorted(self.aliases),
            "soft_labels": sorted(self.soft_labels),
        }

    @classmethod
    def from_json(cls, value: Any) -> PatternEntry:
        payload = as_dict(value)
        return cls(
            id=as_str(payload.get("id")),
            level=as_str(payload.get("level")),
            cluster=as_str(payload.get("cluster")),
            statement=as_str(payload.get("statement")),
            tags=tuple(sorted(as_str(item) for item in as_list(payload.get("tags")))),
            applicability=tuple(
                sorted(as_str(item) for item in as_list(payload.get("applicability")))
            ),
            evidence=tuple(Evidence.from_json(item) for item in as_list(payload.get("evidence"))),
            counterexamples=tuple(
                Evidence.from_json(item) for item in as_list(payload.get("counterexamples"))
            ),
            confidence=as_str(payload.get("confidence"), "中"),
            falsification=as_str(payload.get("falsification")),
            revision=as_int(payload.get("revision"), 1),
            status=as_str(payload.get("status"), "active"),
            cross_domains=tuple(
                sorted(as_str(item) for item in as_list(payload.get("cross_domains")))
            ),
            boundaries=tuple(sorted(as_str(item) for item in as_list(payload.get("boundaries")))),
            anti_patterns=tuple(
                sorted(as_str(item) for item in as_list(payload.get("anti_patterns")))
            ),
            drilldown=tuple(as_str(item) for item in as_list(payload.get("drilldown"))),
            control_group=tuple(
                sorted(as_str(item) for item in as_list(payload.get("control_group")))
            ),
            claim_kind=as_str(payload.get("claim_kind")),
            source=as_str(payload.get("source"), "real"),
            aliases=tuple(sorted(as_str(item) for item in as_list(payload.get("aliases")))),
            soft_labels=tuple(sorted(as_str(item) for item in as_list(payload.get("soft_labels")))),
        )


# --------------------------------------------------------------------------- 四层 schema 校验


def validate_entry(entry: PatternEntry) -> tuple[str, ...]:
    """四层可证伪性（规律库 §B / L3 卡红线 3–5）。空元组 = 可入库。"""
    problems: list[str] = []
    if not entry.id:
        problems.append("条目缺稳定 id")
    if entry.level not in LEVELS:
        problems.append(f"level 必须是 {LEVELS} 之一，实际 {entry.level!r}")
    if not entry.cluster:
        problems.append("条目缺 cluster（domain.id）")
    if not entry.statement:
        problems.append("条目缺 statement")
    if entry.status not in STATUSES:
        problems.append(f"status 非法：{entry.status!r}")
    if entry.source not in SOURCES:
        problems.append(f"source 非法：{entry.source!r}")

    if entry.level == "L1" and not any(
        item.path and item.kind == "正例" for item in entry.evidence
    ):
        problems.append("L1 结构事实必须带 file:line 代码证据")
    if entry.level == "L2":
        if not entry.counterexamples:
            problems.append("L2 缺反例位（红线 3：无反例位的条目禁止入库）")
        if not any(item.repo for item in entry.counterexamples):
            problems.append("L2 反例位必须指向真实仓库")
    if entry.level == "L3" and len(set(entry.cross_domains)) < 2:
        problems.append("L3 缺 ≥2 个方向的跨域证据（红线 4）")
    if entry.level == "L4":
        if not entry.boundaries:
            problems.append("L4 缺适用边界")
        if not entry.anti_patterns:
            problems.append("L4 缺反模式清单")
        if len(entry.drilldown) < 3:
            problems.append("L4 下钻链需至少 L3→L2→L1 三段")
    if entry.claim_kind == "breakout_gene":
        if not entry.control_group:
            problems.append("「爆火基因」类断言缺对照组（红线 5）")
        if not any(item.repo in entry.control_group for item in entry.counterexamples):
            problems.append("对照组必须作为反例证据留痕")
    return tuple(problems)


def validate_drilldown(entry: PatternEntry, index: Mapping[str, PatternEntry]) -> tuple[str, ...]:
    """L4 必须能逐级下钻到 L1 代码证据；不能下钻 = 本质论，禁止入库（T4）。"""
    if entry.level != "L4":
        return ()
    if len(entry.drilldown) < 3:
        return ("L4 下钻链不足三段",)
    ladder: list[str] = []
    for pid in entry.drilldown:
        target = index.get(pid)
        if target is None:
            return (f"下钻目标 {pid} 不存在",)
        if target.level in ("L3", "L2", "L1"):
            ladder.append(target.level)
    if ladder != ["L3", "L2", "L1"]:
        return (f"下钻链层级不是 L3→L2→L1：{ladder}",)
    tail = index[entry.drilldown[-1]]
    if not any(item.path for item in tail.evidence):
        return ("下钻链末端 L1 缺 file:line 代码证据",)
    return ()


def validate_library(entries: Sequence[PatternEntry]) -> tuple[str, ...]:
    problems: list[str] = []
    index: dict[str, PatternEntry] = {}
    for entry in entries:
        if entry.id in index:
            problems.append(f"条目 id 重复：{entry.id}")
        index[entry.id] = entry
        problems.extend(f"{entry.id}: {text}" for text in validate_entry(entry))
    for entry in entries:
        if entry.level == "L4":
            problems.extend(f"{entry.id}: {text}" for text in validate_drilldown(entry, index))
    return tuple(problems)


def assert_storable(entries: Sequence[PatternEntry]) -> None:
    """写真源前的最后一道闸：schema 全过 + 真源纯净（S4）。"""
    problems = list(validate_library(entries))
    synthetic = sorted({entry.id for entry in entries if entry.source == "synthetic"})
    if synthetic:
        problems.append(f"真源禁止写入合成条目（S4）：{', '.join(synthetic)}")
    if problems:
        raise PatternError("；".join(problems))


# --------------------------------------------------------------------------- 特征 / Jaccard


def flatten_featcard(card: Mapping[str, Any]) -> tuple[str, ...]:
    """L0 特征卡 → 稀疏布尔特征向量（设计方案 §4.3），确定性排序。"""
    features: set[str] = set()
    for group in ("parallel", "cache"):
        hits = as_dict(as_dict(card.get(group)).get("hits"))
        for key, value in hits.items():
            if as_bool(value):
                features.add(f"{group}.hits.{as_str(key)}")
    hardware = as_dict(card.get("hardware"))
    for field in ("vendors", "arch_gates", "kernel_langs"):
        for value in as_list(hardware.get(field)):
            text = as_str(value)
            if text:
                features.add(f"hardware.{field}.{text}")
    governance = as_dict(card.get("governance"))
    if as_bool(governance.get("has_governance_docs")):
        features.add("governance.has_governance_docs")
    org_type = as_str(governance.get("org_type"))
    if org_type:
        features.add(f"governance.org_type.{org_type}")
    license_name = as_str(governance.get("license"))
    if license_name:
        features.add(f"governance.license.{license_name}")
    return tuple(sorted(features))


def soft_labels_for(features: Sequence[str]) -> tuple[str, ...]:
    labels = {
        label
        for feature in features
        for prefix, label in SOFT_LABEL_PREFIXES
        if feature.startswith(prefix)
    }
    return tuple(sorted(labels))


def code_evidence_from_card(card: Mapping[str, Any], repo: str) -> tuple[Evidence, ...]:
    """从特征卡 parallel/cache 的 evidence 抽 file:line（L1 代码证据来源）。"""
    found: list[Evidence] = []
    for group in ("parallel", "cache"):
        raw = as_dict(as_dict(card.get(group)).get("evidence"))
        for axis in sorted(raw):
            for item in as_list(raw[axis]):
                payload = as_dict(item)
                path = as_str(payload.get("file"))
                line = as_int(payload.get("line"))
                if path and line > 0:
                    found.append(
                        Evidence(repo=repo, kind="正例", path=f"{path}:{line}", note=as_str(axis))
                    )
    return tuple(sorted(found, key=lambda item: (item.path, item.note)))


def weighted_jaccard(
    left: Sequence[str],
    right: Sequence[str],
    weights: Mapping[str, float] | None = None,
) -> float:
    """加权 Jaccard；按特征排序后累加，保证浮点结果可复现。空并集 → 0.0。"""
    set_left, set_right = set(left), set(right)
    union = set_left | set_right
    if not union:
        return 0.0
    table = weights or {}

    def weight(feature: str) -> float:
        return float(table.get(feature.split(".")[0], 1.0))

    intersection = sum(weight(item) for item in sorted(set_left & set_right))
    total = sum(weight(item) for item in sorted(union))
    if total <= 0:
        return 0.0
    return r4(intersection / total)


# --------------------------------------------------------------------------- 三态召回（零 LLM）


@dataclass(frozen=True)
class ProjectFeatures:
    repo: str
    domain: str | None
    features: tuple[str, ...]
    soft_labels: tuple[str, ...]

    @classmethod
    def from_card(cls, card: Mapping[str, Any], domain: str | None) -> ProjectFeatures:
        identity = as_dict(card.get("identity"))
        features = flatten_featcard(card)
        return cls(
            repo=as_str(identity.get("repo")),
            domain=domain,
            features=features,
            soft_labels=soft_labels_for(features),
        )


@dataclass(frozen=True)
class RecallRow:
    project: str
    domain: str | None
    state: str
    pattern_id: str
    similarity: float
    matched_fields: tuple[str, ...]
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "domain": self.domain,
            "state": self.state,
            "pattern_id": self.pattern_id,
            "similarity": self.similarity,
            "matched_fields": list(self.matched_fields),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CounterexampleCandidate:
    project: str
    pattern_id: str
    reason: str
    scope_mismatch: bool  # True = 适用域未命中（设计方案 §4.1 丢弃，不挂到条目）

    def to_json(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "pattern_id": self.pattern_id,
            "reason": self.reason,
            "scope_mismatch": self.scope_mismatch,
        }


@dataclass(frozen=True)
class RecallResult:
    rows: tuple[RecallRow, ...]
    candidates: tuple[CounterexampleCandidate, ...]


def _applicable(project_domain: str | None, entry: PatternEntry) -> bool:
    """硬 gating：domain.id 必须命中条目的 cluster / 适用域 / 跨域方向。"""
    if project_domain is None:
        return False
    return (
        project_domain == entry.cluster
        or project_domain in entry.applicability
        or project_domain in entry.cross_domains
    )


def recall(
    projects: Sequence[ProjectFeatures],
    entries: Sequence[PatternEntry],
    *,
    similarity_threshold: float = 0.5,
    weights: Mapping[str, float] | None = None,
) -> RecallResult:
    """确定性三态召回：已命中 / 新模式候选 / 不适用。零 LLM、无 I/O、无时钟。

    - 硬 gating（`domain.id` + 关键结构特征）未过 → `not_applicable`，自动进反例候选池
      （L3 卡 T3）。按设计方案 §4.1，适用域未命中者 `scope_mismatch=True`，只入候选池、
      不挂到任何条目的反例位（等于丢弃其正例价值）。
    - 硬 gating 过了但最高相似度未达阈值 → `new_candidate`（新模式靠 cluster_run 补位），
      同时按设计方案 §4.1「未采用 = 反例候选」生成 `scope_mismatch=False` 的候选。
    - 达到阈值 → `matched`（正例）。
    """
    active = tuple(
        sorted(
            (entry for entry in entries if entry.status != "falsified"),
            key=lambda item: item.id,
        )
    )
    rows: list[RecallRow] = []
    candidates: list[CounterexampleCandidate] = []
    for project in sorted(projects, key=lambda item: item.repo):
        applicable = [entry for entry in active if _applicable(project.domain, entry)]
        if not applicable:
            rows.append(
                RecallRow(
                    project=project.repo,
                    domain=project.domain,
                    state=STATE_NOT_APPLICABLE,
                    pattern_id="",
                    similarity=0.0,
                    matched_fields=(),
                    reason="domain.id 未命中任何条目的适用域",
                )
            )
            candidates.append(
                CounterexampleCandidate(
                    project=project.repo,
                    pattern_id="",
                    reason="不适用：无适用条目",
                    scope_mismatch=True,
                )
            )
            continue

        scored = [
            (
                weighted_jaccard(project.features, entry.tags, weights),
                entry.id,
                entry,
            )
            for entry in applicable
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        best_score, best_id, best_entry = scored[0]
        shared = tuple(sorted(set(project.features) & set(best_entry.tags)))
        if best_score >= similarity_threshold:
            rows.append(
                RecallRow(
                    project=project.repo,
                    domain=project.domain,
                    state=STATE_MATCHED,
                    pattern_id=best_id,
                    similarity=best_score,
                    matched_fields=shared,
                    reason="硬 gating 通过且加权 Jaccard 达阈值",
                )
            )
        else:
            rows.append(
                RecallRow(
                    project=project.repo,
                    domain=project.domain,
                    state=STATE_NEW_CANDIDATE,
                    pattern_id=best_id,
                    similarity=best_score,
                    matched_fields=shared,
                    reason="适用域命中但关键结构特征未命中 → 新模式候选 + 反例候选",
                )
            )
            candidates.append(
                CounterexampleCandidate(
                    project=project.repo,
                    pattern_id=best_id,
                    reason="未采用：适用域命中但关键特征未命中",
                    scope_mismatch=False,
                )
            )
    return RecallResult(
        rows=tuple(sorted(rows, key=lambda item: (item.project, item.pattern_id))),
        candidates=tuple(
            sorted(candidates, key=lambda item: (item.project, item.pattern_id, item.reason))
        ),
    )


# --------------------------------------------------------------------------- 增量 merge（ops）


@dataclass(frozen=True)
class Op:
    op: str
    id: str
    reason: str = ""
    target_id: str = ""
    entry: PatternEntry | None = None
    evidence: tuple[Evidence, ...] = ()
    statement: str = ""
    applicability: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "id": self.id,
            "reason": self.reason,
            "target_id": self.target_id,
            "entry": self.entry.to_json() if self.entry else None,
            "evidence": [item.to_json() for item in self.evidence],
            "statement": self.statement,
            "applicability": list(self.applicability),
        }

    @classmethod
    def from_json(cls, value: Any) -> Op:
        payload = as_dict(value)
        raw_entry = payload.get("entry")
        return cls(
            op=as_str(payload.get("op")),
            id=as_str(payload.get("id")),
            reason=as_str(payload.get("reason")),
            target_id=as_str(payload.get("target_id")),
            entry=PatternEntry.from_json(raw_entry) if isinstance(raw_entry, dict) else None,
            evidence=tuple(Evidence.from_json(item) for item in as_list(payload.get("evidence"))),
            statement=as_str(payload.get("statement")),
            applicability=tuple(
                sorted(as_str(item) for item in as_list(payload.get("applicability")))
            ),
        )


def _raise_confidence(current: str) -> str:
    return {"低": "中", "中": "高"}.get(current, "高")


def apply_ops(
    entries: Sequence[PatternEntry], ops: Sequence[Op]
) -> tuple[tuple[PatternEntry, ...], tuple[str, ...]]:
    """把 ops 追加修订到现有条目；失效条目只标 falsified、永不删除（红线 6）。"""
    index: dict[str, PatternEntry] = {entry.id: entry for entry in entries}
    warnings: list[str] = []
    for operation in ops:
        if operation.op not in OPS:
            warnings.append(f"未知 op {operation.op!r}，跳过")
            continue
        if operation.op == "add":
            if operation.entry is None:
                warnings.append(f"add {operation.id} 缺 entry，跳过")
                continue
            index[operation.entry.id] = operation.entry
            continue
        target = index.get(operation.id)
        if target is None:
            warnings.append(f"{operation.op} 目标 {operation.id} 不存在，跳过")
            continue
        revision = target.revision + 1
        if operation.op == "strengthen":
            index[operation.id] = replace(
                target,
                evidence=target.evidence + operation.evidence,
                confidence=_raise_confidence(target.confidence),
                revision=revision,
            )
        elif operation.op == "weaken":
            index[operation.id] = replace(
                target,
                counterexamples=target.counterexamples + operation.evidence,
                status="weakened",
                revision=revision,
            )
        elif operation.op == "refine":
            index[operation.id] = replace(
                target,
                statement=operation.statement or target.statement,
                applicability=operation.applicability or target.applicability,
                revision=revision,
            )
        elif operation.op == "falsify":
            index[operation.id] = replace(target, status="falsified", revision=revision)
        elif operation.op == "merge":
            other = index.get(operation.target_id)
            if other is None:
                warnings.append(f"merge 目标 {operation.target_id} 不存在，跳过")
                continue
            merged = replace(
                target,
                tags=tuple(sorted(set(target.tags) | set(other.tags))),
                evidence=target.evidence + other.evidence,
                counterexamples=target.counterexamples + other.counterexamples,
                aliases=tuple(sorted(set(target.aliases) | {other.id})),
                status="active",
                revision=max(target.revision, other.revision) + 1,
            )
            index[operation.id] = merged
            # 旧 ID 保留为 alias；被合并条目标 falsified 而非删除。
            index[other.id] = replace(other, status="falsified", revision=other.revision + 1)
    return tuple(index[key] for key in sorted(index)), tuple(warnings)


def needs_reconcile(incremental_runs: int, every: int) -> bool:
    """每 N 次增量 run 做一次全量 reconcile（规律库 §E，受控时钟驱动）。"""
    return every > 0 and incremental_runs > 0 and incremental_runs % every == 0


def should_cross_domain(
    l2_entries: int, cluster_runs: int, *, min_entries: int, every_runs: int
) -> bool:
    """跨域抽象：L2 条目 ≥N 或每 N 次簇内 run（规律库 §E）。"""
    if min_entries > 0 and l2_entries >= min_entries:
        return True
    return every_runs > 0 and cluster_runs > 0 and cluster_runs % every_runs == 0


# --------------------------------------------------------------------------- 自检四问（规律库 §G）


@dataclass(frozen=True)
class SelfCheck:
    has_drilldown_evidence: bool
    new_counterexamples: int
    has_cross_domain_evidence: bool
    manual_review_target: str
    warnings: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "q1_has_drilldown_evidence": self.has_drilldown_evidence,
            "q2_new_counterexamples": self.new_counterexamples,
            "q3_has_cross_domain_evidence": self.has_cross_domain_evidence,
            "q4_manual_review_target": self.manual_review_target,
            "warnings": list(self.warnings),
        }


def build_self_check(
    entries: Sequence[PatternEntry],
    candidates: Sequence[CounterexampleCandidate],
) -> SelfCheck:
    """四问必答；无反例显式告警；抽检位必填。"""
    warnings: list[str] = []
    attachable = [item for item in candidates if not item.scope_mismatch]
    if not attachable:
        warnings.append("本轮无可挂接反例 → 幸存者偏差风险（L3 卡红线 3 / T6）")
    has_drilldown = any(
        entry.level == "L1" and any(item.path for item in entry.evidence) for entry in entries
    )
    has_cross_domain = any(
        entry.level == "L3" and len(set(entry.cross_domains)) >= 2 for entry in entries
    )
    by_revision = sorted(entries, key=lambda item: (-item.revision, item.id))
    if by_revision:
        manual = by_revision[0].id
    elif candidates:
        manual = f"候选项目 {sorted({item.project for item in candidates})[0]}（无条目可抽检）"
    else:
        manual = "（本轮无条目、无候选，无可抽检位）"
        warnings.append("抽检位无对象：本轮既无条目也无候选")
    return SelfCheck(
        has_drilldown_evidence=has_drilldown,
        new_counterexamples=len(attachable),
        has_cross_domain_evidence=has_cross_domain,
        manual_review_target=manual,
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------- 真源 I/O


def load_library(path: Any) -> tuple[PatternEntry, ...]:
    if not path.exists():
        return ()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return ()
    if not isinstance(payload, list):
        raise PatternError(f"{path}: 规律库顶层必须是条目数组")
    return tuple(PatternEntry.from_json(item) for item in payload)


def save_library(path: Any, entries: Sequence[PatternEntry]) -> None:
    """写规律库：先校验真源纯净 + 全量 schema；再断言 append-only（旧 id 一个都不能少）。"""
    assert_storable(entries)
    existing_ids = {entry.id for entry in load_library(path)}
    new_ids = {entry.id for entry in entries}
    lost = sorted(existing_ids - new_ids)
    if lost:
        raise PatternError(f"patterns/ append-only 被破坏，丢失 id：{', '.join(lost)}")
    ordered = [entry.to_json() for entry in sorted(entries, key=lambda item: item.id)]
    atomic_write_text(path, yaml.safe_dump(ordered, sort_keys=True, allow_unicode=True))


def append_ops(path: Any, run_id: str, ops: Sequence[Op]) -> None:
    """ops 追加修订日志（真源 append-only）。"""
    for operation in ops:
        append_jsonl(path, {"run_id": run_id, **operation.to_json()})
