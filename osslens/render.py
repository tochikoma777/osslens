"""报告渲染（Markdown，字节一致）。

结构写死为执行手册附录 A 的五个区块，顺序不可变：
运行元数据 → 体检事实 → 特征卡摘要 → 洞见 → 外部资料。
L1 只在**已有区块内**追加证据 / 依赖图 / 成本行，不新增第六区块。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .collect import ExternalProbe, SourceNote
from .depth import DepthDecision
from .featcard import depgraph_mermaid
from .llm import Context, Insight
from .util import as_int, as_str, fmt_iso

DASH = "—"

# D10 = A：报告口径的显式字样（写死，防稀释）。改动需同步改 tests/test_l2.py 的断言。
D10_WORDING = "本次分析的成本（不含开发期重复调用）；账户累计见 cost"

# 报告头部成本异常区块的标记行（站点 site._ANOMALY_MARKER 必须与此完全一致；
# 两侧各自保留字面量，由 tests 的标记一致性守护测试防漂移）。
COST_ANOMALY_MARKER = "> ⚠ **成本异常（仅标注，不阻断）**"


def detect_cost_anomalies(
    *,
    week_tokens: int,
    month_tokens: int,
    run_tokens: int,
    weekly_tokens: int,
    monthly_tokens: int,
    history: Sequence[int],
) -> tuple[str, ...]:
    """成本异常判定（只标注、不阻断）；三条规则与 docs/成本预算.md §5 一致。

    周用量 > 周额度 × 50% · 月用量 > 月额度 × 80% · 本次 > 同仓库近期调用中位数 × 3
    （中位数为 0 时跳过，不拿 0 冒充）。阈值口径沿用 cli._cost_line 原有实现，
    抽成纯函数只为可专门断言，不改变任何判定结果或文案。
    """
    anomalies: list[str] = []
    if week_tokens > weekly_tokens * 0.5:
        anomalies.append("本周用量 > 周额度 50%")
    if month_tokens > monthly_tokens * 0.8:
        anomalies.append("本月用量 > 月额度 80%")
    ordered = sorted(history)
    if run_tokens and ordered:
        median = ordered[len(ordered) // 2]
        if median > 0 and run_tokens > median * 3:
            anomalies.append(f"本次 {run_tokens} tok > 近期中位数 {median} tok 的 3 倍")
    return tuple(anomalies)


def cost_anomaly_block(cost: CostLine | None) -> list[str]:
    """报告头部独立区块（Q-K3-1′ 选项①）：不与成本表格混排，只标注、不阻断。

    anomalies 为空时不渲染任何行 → 现有报告字节完全不变（幂等/五区块契约不破）。
    """
    if cost is None or not cost.anomalies:
        return []
    lines = [COST_ANOMALY_MARKER, ">"]
    lines.extend(f"> - {item}" for item in cost.anomalies)
    lines.append("")
    return lines


@dataclass(frozen=True)
class CostLine:
    run_cost: float | None
    calls: int
    prompt_tokens: int
    cache_hit_tokens: int
    completion_tokens: int
    source: str
    week_cost: float
    week_tokens: int
    month_cost: float
    month_tokens: int
    model_prices: tuple[str, ...]
    anomalies: tuple[str, ...]


@dataclass(frozen=True)
class ReportInputs:
    owner: str
    repo: str
    as_of: datetime
    channel: str
    domain: str
    requested_depth: str
    decision: DepthDecision
    card: dict[str, Any]
    snapshot_sha256: str
    snapshot_notes: tuple[SourceNote, ...]
    featcard_relpath: str
    external: ExternalProbe | None = None
    insight: Insight | None = None
    insight_reason: str = ""
    context: Context | None = None
    cost: CostLine | None = None


def render_report(inputs: ReportInputs) -> str:
    lines: list[str] = []
    lines.append(f"# 开源项目分析 · {inputs.owner}/{inputs.repo}")
    lines.append("")
    lines.extend(cost_anomaly_block(inputs.cost))
    lines.extend(_metadata_section(inputs))
    lines.extend(_facts_section(inputs))
    lines.extend(_featcard_section(inputs))
    lines.extend(_insight_section(inputs))
    lines.extend(_external_section(inputs))
    return "\n".join(lines).rstrip("\n") + "\n"


def _metadata_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    identity = _section(card, "identity")
    decision = inputs.decision
    depth_cell = decision.actual
    if decision.downgraded:
        depth_cell = f"{decision.actual}（降级：{decision.reason_text}）"
    lines = [
        "## 运行元数据",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 仓库 | {inputs.owner}/{inputs.repo} |",
        f"| commit | `{_cell(as_str(identity.get('commit')))}` |",
        f"| 分析基准时间 (as-of) | {fmt_iso(inputs.as_of)} |",
        f"| 通道 / 领域 | {inputs.channel} / {inputs.domain} |",
        f"| 请求档位 (requested_depth) | {decision.requested} |",
        f"| **实际档位** (actual_depth) | {depth_cell} |",
        f"| 降级原因 (reason) | {decision.reason} — {decision.reason_text} |",
        f"| 配额状态 (quota_state) | {decision.quota.summary()} |",
        f"| 快照 sha256 | `{inputs.snapshot_sha256}` |",
    ]
    lines.extend(_cost_rows(inputs.cost))
    lines.extend(["", "**档位决策链路**：", ""])
    lines.extend(f"{index}. {step}" for index, step in enumerate(decision.chain, start=1))
    lines.extend(
        [
            "",
            "**上下文组装**（裁剪发生在调用之前）：",
            "",
            "| 块 | 优先级 | 估算 token |",
            "|---|---|---|",
        ]
    )
    if inputs.context is None:
        lines.extend(
            [
                f"| featcard | 1 | {DASH} |",
                f"| readme | 2 | {DASH} |",
                f"| source_files | 4 | {DASH} |",
                "",
                f"- 丢弃：{DASH}（{decision.actual} 档不组装上下文，未发起任何模型请求）",
                f"- 合计 0 / 上限 {decision.prompt_token_limit}",
            ]
        )
    else:
        for block in inputs.context.blocks:
            lines.append(f"| {block.name} | {block.priority} | {block.tokens:,} |")
        dropped = "、".join(inputs.context.dropped) if inputs.context.dropped else DASH
        lines.append("")
        lines.append(f"- 丢弃：{dropped}")
        lines.append(f"- 合计 {inputs.context.tokens:,} / 上限 {decision.prompt_token_limit:,}")
    lines.append("")
    return lines


def _cost_rows(cost: CostLine | None) -> list[str]:
    if cost is None:
        return []
    if cost.run_cost is None:
        run_cell = f"{DASH}（未调用）"
    else:
        run_cell = f"¥{cost.run_cost:.4f}（模型调用 {cost.calls} 次）"
    detail = (
        f"输入 {cost.prompt_tokens:,} tok / 命中 {cost.cache_hit_tokens:,} tok / "
        f"输出 {cost.completion_tokens:,} tok"
    )
    rows = [
        f"| 成本说明 | 本次 {run_cell}；{detail} |",
        f"| 累计 | 本周 ¥{cost.week_cost:.4f} / {cost.week_tokens:,} tok；"
        f"本月 ¥{cost.month_cost:.4f} / {cost.month_tokens:,} tok |",
    ]
    if cost.model_prices:
        rows.append(f"| 单价 | {cost.model_prices[0]} |")
    rows.append(
        f"| 口径 | {D10_WORDING}；成本说明同 as-of 重跑不变（幂等优先）；"
        "两者不一致是设计，不是 bug |"
    )
    return rows


def _facts_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    scale = _section(card, "scale")
    structure = _section(card, "structure")
    governance = _section(card, "governance")
    signals = _section(card, "signals")
    identity = _section(card, "identity")
    deps = _section(card, "deps")

    contributors = _int_or_none(scale.get("contributors"))
    bus_factor = _ratio(signals.get("bus_factor_top1_share"))
    top10_share = _ratio(scale.get("top10_share"))
    files = _int_or_none(structure.get("files"))
    total_bytes = _int_or_none(structure.get("bytes"))
    commits_90d = _whole(scale.get("commits_90d"))
    commits_365d = _whole(scale.get("commits_365d"))
    last_commit = _cell(as_str(scale.get("last_commit")))
    days_since = _whole(signals.get("days_since_commit"))
    releases_365d = _whole(scale.get("release_count_365d"))
    org_type = _cell(as_str(governance.get("org_type")))
    license_id = _cell(as_str(governance.get("license")))
    lines = [
        "## 体检事实（确定性，零 LLM）",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        _row("Star / Fork", f"{_whole(scale.get('stars'))} / {_whole(scale.get('forks'))}"),
        _row("被依赖 (Used by)", _whole(scale.get("used_by"))),
        _row("贡献者 / Top1 占比", f"{_whole(contributors)} / {bus_factor}"),
        _row("Top10 贡献集中度", top10_share),
        _row("90 天 / 365 天提交", f"{commits_90d} / {commits_365d}"),
        _row("最近提交 / 距今天数", f"{last_commit} / {days_since}"),
        _row("维护状态", _cell(as_str(signals.get("maintenance_state")))),
        _row("项目年龄 / 发布数(365d)", f"{_age(identity.get('age_days'))} / {releases_365d}"),
        _row("组织类型 / 许可证", f"{org_type} / {license_id}"),
        _row("文件数 / 体积", f"{_whole(files)} / {_bytes(total_bytes)}"),
        _row("内部模块依赖边", _whole(deps.get("internal_edge_count"))),
        "",
        f"**语言构成**：{_languages(_section(card, 'lang').get('shares'))}",
        "",
        "**模块体量 Top10**",
        "",
        "| 模块 | 文件数 | 字节 |",
        "|---|---|---|",
    ]
    modules = _rows(structure.get("top_modules"))[:10]
    if modules:
        for row in modules:
            lines.append(
                f"| {_cell(as_str(row.get('path')))} | {_whole(row.get('files'))} | "
                f"{_whole(row.get('bytes'))} |"
            )
    else:
        lines.append(f"| {DASH} | {DASH} | {DASH} |")
    lines.append("")
    lines.extend(_degraded_lines(inputs.snapshot_notes))
    return lines


def _featcard_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    structure = _section(card, "structure")
    parallel = _section(card, "parallel")
    cache = _section(card, "cache")
    hardware = _section(card, "hardware")
    deps = _section(card, "deps")
    sources = _section(card, "sources")
    gov_docs = "是" if _section(card, "governance").get("has_governance_docs") else "否"
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    lines = [
        "## 特征卡摘要",
        "",
        f"- 卡文件：`{inputs.featcard_relpath}`（schema {as_str(card.get('schema_version'))}）",
        f"- 入口文件：{', '.join(entrypoints) if entrypoints else DASH}",
        f"- 最大目录深度：{_whole(structure.get('max_depth'))}；"
        f"monorepo：{'是' if structure.get('monorepo') else '否'}",
        f"- 源码切片：{len(_rows(sources.get('files')))} 个文件"
        f"（tarball `{as_str(sources.get('tarball_sha256'))[:16]}`）",
        f"- 依赖：直接 / 传递 = {_whole(deps.get('direct'))} / {_whole(deps.get('transitive'))}"
        "（L1 未解析清单文件）",
        "",
        "**并行轴**",
        "",
    ]
    lines.extend(_evidence_block(parallel, "并行"))
    lines.extend(["", "**缓存**", ""])
    lines.extend(_evidence_block(cache, "缓存"))
    lines.extend(
        [
            "",
            f"- 硬件：vendors={_list(hardware.get('vendors'))}、"
            f"arch_gates={_list(hardware.get('arch_gates'))}、"
            f"kernel_langs={_list(hardware.get('kernel_langs'))}",
            f"- 治理文档：{gov_docs}",
            "",
            "**依赖图**（内部模块 import 边，节点/边排序后输出）",
            "",
            "```mermaid",
            depgraph_mermaid(_graph_dict(deps)),
            "```",
            "",
            "**已知限制**：",
            "",
        ]
    )
    limitations = [as_str(item) for item in card.get("limitations", []) if as_str(item)]
    lines.extend(f"- {item}" for item in (limitations or [DASH]))
    lines.append("")
    return lines


def _evidence_block(section: dict[str, Any], label: str) -> list[str]:
    hits = _section(section, "hits")
    evidence = _section(section, "evidence")
    if not hits:
        return [f"- {label}：{DASH}"]
    lines: list[str] = []
    for axis in sorted(hits):
        if hits.get(axis):
            rows = _rows(evidence.get(axis))
            lines.append(f"- {label} `{axis}` = true（证据 {len(rows)} 条）")
            for row in rows:
                lines.append(
                    f"  - `{as_str(row.get('file'))}:{as_int(row.get('line'))}` — "
                    f"`{as_str(row.get('snippet'))}`"
                )
        else:
            lines.append(f"- {label} `{axis}` = false（无证据）")
    return lines


def _insight_section(inputs: ReportInputs) -> list[str]:
    if inputs.insight is not None and inputs.insight.items:
        lines = [
            "## 洞见",
            "",
            "| id | 选择 | 放弃的替代 | 代价 | 证据 |",
            "|---|---|---|---|---|",
        ]
        for item in inputs.insight.items:
            lines.append(
                f"| {item.id} | {item.chose} | {item.alternative} | {item.cost} | "
                f"`{item.evidence}` |"
            )
        lines.extend(["", f"- 置信度：{inputs.insight.confidence}"])
        if inputs.insight.paradigm_tags:
            # 报告级架构范式标签（受控词表，确定性排序）；供站点标签过滤预生成解析
            tags = "、".join(inputs.insight.paradigm_tags)
            lines.append(f"- 架构范式标签：{tags}")
        if inputs.insight.dropped:
            lines.append(f"- 被代码丢弃的条目：{len(inputs.insight.dropped)} 条")
            lines.extend(f"  - {reason}" for reason in inputs.insight.dropped)
        lines.append("")
        return lines

    lines = ["## 洞见", "", DASH]
    if inputs.insight_reason:
        lines.extend(["", f"> fast 档未产出洞见：{inputs.insight_reason}"])
    lines.append("")
    return lines


def _external_section(inputs: ReportInputs) -> list[str]:
    probe = inputs.external
    if probe is None:
        return [
            "## 外部资料",
            "",
            "- DeepWiki / Zread：不可用（未索引）",
            "- 判定原因：本次未启用外部工具探测",
            "",
        ]

    lines = [
        "## 外部资料",
        "",
        f"- 来源：{probe.source}",
        f"- url：{probe.url}",
        f"- fetched_at：{probe.fetched_at or DASH}",
        f"- sha256：`{probe.sha256 or DASH}`",
        f"- 判定：{probe.status} — {probe.reason}",
    ]
    if probe.raw_relpath:
        lines.append(f"- 原文快照：`{probe.raw_relpath}`（与判定元数据分文件存放）")
    if probe.status == "miss":
        lines.append("- 结论：不可用（未索引）")
    elif probe.status != "hit":
        lines.append("- 结论：未获得")
    lines.append("")
    return lines


def _degraded_lines(notes: tuple[SourceNote, ...]) -> list[str]:
    failed = [note for note in notes if note.status in ("failed", "truncated")]
    unavailable = [note for note in notes if note.status == "unavailable"]
    lines: list[str] = []
    if failed:
        lines.append("**本次降级来源**：")
        lines.append("")
        lines.extend(f"- `{note.source}`（{note.status}）：{note.reason}" for note in failed)
        lines.append("")
    if unavailable:
        lines.append("**未获得的指标**：")
        lines.append("")
        lines.extend(f"- `{note.source}`：{note.reason}" for note in unavailable)
        lines.append("")
    return lines


def _graph_dict(deps: dict[str, Any]) -> dict[str, Any]:
    graph = deps.get("graph")
    return graph if isinstance(graph, dict) else {}


def _section(card: dict[str, Any], key: str) -> dict[str, Any]:
    value = card.get(key)
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _whole(value: Any) -> str:
    number = _int_or_none(value)
    return DASH if number is None else f"{number:,}"


def _ratio(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DASH
    return f"{float(value) * 100:.2f}%"


def _age(value: Any) -> str:
    number = _int_or_none(value)
    return DASH if number is None else f"{number:,} 天"


def _bytes(value: int | None) -> str:
    if value is None:
        return DASH
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def _cell(text: str) -> str:
    return text if text else DASH


def _row(label: str, value: str) -> str:
    return f"| {label} | {value} |"


def _languages(shares: Any) -> str:
    if not isinstance(shares, dict) or not shares:
        return DASH
    pairs = sorted((as_str(name), value) for name, value in shares.items())
    return "、".join(
        f"{name} {float(value) * 100:.2f}%"
        for name, value in pairs
        if isinstance(value, (int, float))
    )


def _list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "[]"
    return "[" + ", ".join(sorted(as_str(item) for item in value)) + "]"


__all__ = [
    "COST_ANOMALY_MARKER",
    "CostLine",
    "DASH",
    "ReportInputs",
    "render_report",
    "cost_anomaly_block",
    "detect_cost_anomalies",
]
