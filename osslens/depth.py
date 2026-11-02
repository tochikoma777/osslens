"""档位四层 + 预算闸门 + Ledger（设计方案 §2 / §9 / §11）。

四层：
  L1 通道基线 → L2 周配额 → L3 预算闸门 → L4 人工 override
★ 降级必须双写：报告「运行元数据」块 + `costs.jsonl`（红线 #10）。
★ L4 可绕过 L1/L2，**不能绕过 L3**。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
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
REQUESTED_DEPTHS = ("auto", "off", "fast", "strong")

EVENT_CALL = "call"
EVENT_DOWNGRADE = "downgrade"
EVENT_BLOCKED = "blocked"
EVENT_CACHE_HIT = "cache_hit"
EVENT_KINDS = (EVENT_CALL, EVENT_DOWNGRADE, EVENT_BLOCKED, EVENT_CACHE_HIT)

REASON_TEXT = {
    "explicit_off": "显式请求 off 档（零 LLM）",
    "no_credentials": "未配置 LLM 凭据（api_key / base_url / model 缺一）",
    "weekly_quota_exhausted": "本周配额已用满",
    "budget_blocked": "预算闸门拦截",
    "depth_unavailable_in_l0": "L0 尚未接入 LLM 档位（L1 起启用）",
    "manual_override": "人工 override",
    "baseline": "按通道基线",
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

    def to_json(self) -> dict[str, Any]:
        return {
            "actual_depth": self.actual_depth,
            "as_of": self.as_of,
            "completion_tokens": self.completion_tokens,
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
    budget_week_remaining: int
    budget_month_remaining: int


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


def resolve_depth(
    config: Config,
    *,
    requested: str,
    channel: str,
    as_of: datetime,
    events: Sequence[CostEvent],
    llm_available: bool,
    estimated_prompt_tokens: int = 0,
    credentials_present: bool | None = None,
) -> DepthDecision:
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
        chain.append("L4 人工 override：显式 --depth off（不再评估其它层）")
        return decide("off", "explicit_off", False)

    manual = requested in ("fast", "strong")
    baseline = requested if manual else config.depth.baseline.get(channel, "fast")
    if manual:
        chain.append(f"L4 人工 override：--depth {requested}（绕过 L1 基线 / L2 配额）")
    else:
        chain.append(f"L1 通道基线：{channel} → {baseline}")

    if not present:
        chain.append("凭据：api_key / base_url / model 缺一 → 降级 off（退出码仍为 0）")
        return decide("off", "no_credentials", True)
    chain.append("凭据：齐全")

    # 能力检查先于预算：L0 根本没有 LLM 实现，谈配额/预算没有意义
    if baseline != "off" and not llm_available:
        chain.append("实现能力：fast/strong 尚未接入（LLM 从 L1 起） → 降级 off")
        return decide("off", "depth_unavailable_in_l0", True)

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

    over_budget = (
        estimated_prompt_tokens > per_run_limit
        or quota.tokens_week + estimated_prompt_tokens > quota.tokens_week_limit
        or quota.tokens_month + estimated_prompt_tokens > quota.tokens_month_limit
    )
    if over_budget:
        chain.append(
            f"L3 预算：单选预估 {estimated_prompt_tokens} tok、"
            f"周 {quota.tokens_week}/{quota.tokens_week_limit}、"
            f"月 {quota.tokens_month}/{quota.tokens_month_limit} → 拦截（L4 也不能绕过）"
        )
        return decide("off", "budget_blocked", True)
    chain.append(
        f"L3 预算：单选预估 {estimated_prompt_tokens} tok（上限 {per_run_limit}），"
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
    """
    payload = event.to_json()
    existing = read_jsonl(layout.costs_jsonl)
    if any(record == payload for record in existing):
        return False
    append_jsonl(layout.costs_jsonl, payload)
    return True


def estimate_cost(
    config: Config, *, model: str, prompt_tokens: int, completion_tokens: int
) -> float | None:
    """单价表为空 → 返回 None（渲染为 `—`），绝不内置价格。"""
    entry = config.llm.price_table.get(model)
    if entry is None:
        return None
    cost = (
        prompt_tokens / 1_000_000 * entry.prompt_per_1m
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
    for event in events:
        try:
            when = parse_iso(event.as_of)
        except ValueError:
            continue
        in_week = when >= week_start
        in_month = when >= month_start
        if event.event == EVENT_DOWNGRADE:
            week_downgrades += 1 if in_week else 0
            month_downgrades += 1 if in_month else 0
            continue
        if event.event == EVENT_BLOCKED:
            week_blocked += 1 if in_week else 0
            month_blocked += 1 if in_month else 0
            continue
        if event.event != EVENT_CALL:
            continue
        tokens = event.prompt_tokens + event.completion_tokens
        if in_week:
            week_tokens += tokens
            by_depth[event.depth] = by_depth.get(event.depth, 0) + 1
        if in_month:
            month_tokens += tokens
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
        budget_week_remaining=max(0, config.depth.budget.weekly_tokens - week_tokens),
        budget_month_remaining=max(0, config.depth.budget.monthly_tokens - month_tokens),
    )
