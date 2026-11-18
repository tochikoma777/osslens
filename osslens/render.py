"""报告渲染（Markdown，字节一致）。

v2a 结构：导读 + 6 个阅读模块（定位 / 许可 / 架构 / 工程 / 维护 / 扩展），
参数表与证据下沉到 5 个附录（洞见 / 外部资料 / 运行元数据 / 特征卡 / 体检事实）。
确定性内容仍由代码生成，LLM 只提供带 file:line 证据的取舍判断。
"""

from __future__ import annotations

import re
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

    anomalies 为空时不渲染任何行 → 现有报告字节完全不变（幂等契约不破）。
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
    lines.append(f"# {inputs.owner}/{inputs.repo} 深度分析")
    lines.append("")
    lines.extend(cost_anomaly_block(inputs.cost))
    lines.extend(_lead_section(inputs))
    lines.extend(_positioning_section(inputs))
    lines.extend(_license_section(inputs))
    lines.extend(_architecture_section(inputs))
    lines.extend(_engineering_section(inputs))
    lines.extend(_maintenance_section(inputs))
    lines.extend(_extension_section(inputs))
    lines.extend(_insight_section(inputs))
    lines.extend(_external_section(inputs))
    lines.extend(_metadata_section(inputs))
    lines.extend(_featcard_section(inputs))
    lines.extend(_facts_section(inputs))
    return "\n".join(lines).rstrip("\n") + "\n"


def _first_language(inputs: ReportInputs) -> str:
    shares = _section(inputs.card, "lang").get("shares")
    if not isinstance(shares, dict) or not shares:
        return DASH
    name, value = max(shares.items(), key=lambda pair: float(pair[1] or 0))
    if not isinstance(value, (int, float)):
        return as_str(name)
    return f"{as_str(name)}（{float(value) * 100:.0f}%）"


def _readme_excerpt(inputs: ReportInputs) -> str:
    """从上下文块提取 README 的前两段纯文本，用于「项目是干嘛的」。"""
    if inputs.context is None:
        return ""
    text = ""
    for block in inputs.context.blocks:
        if block.name == "readme":
            text = block.text
            break
    if not text:
        return ""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("##", "#", "```", "![", "[![", "<", "|", "---")):
            continue
        # 去掉图片 / 链接 / HTML，保留可读文字
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line:
            continue
        lines.append(line)
        if len(" ".join(lines)) > 420:
            break
    return " ".join(lines)[:600].strip()


def _lead_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    scale, signals = _section(card, "scale"), _section(card, "signals")
    identity, governance = _section(card, "identity"), _section(card, "governance")
    state = _cell(as_str(signals.get("maintenance_state")))
    license_id = _cell(as_str(governance.get("license")))
    lines = [
        "## 导读",
        "",
        f"> **一句话**：{inputs.owner}/{inputs.repo} 是一个以 "
        f"{_first_language(inputs)}为主的项目，"
        f"约 {_whole(scale.get('stars'))} stars，仓库年龄 {_age(identity.get('age_days'))}，"
        f"近 90 天 {_whole(scale.get('commits_90d'))} 次提交，维护状态「{state}」。",
        ">",
        f"> **先注意**：许可证 {license_id}；"
        "依赖链许可证、模型权重/数据许可、CLA 当前未采集；"
        "以下判断凡未注明证据的，均为仓库信号推断，需人工复核。",
        "",
    ]
    excerpt = _readme_excerpt(inputs)
    lines.append(
        f"**它大概在做什么**：{excerpt}"
        if excerpt
        else "**它大概在做什么**：本次未获得可用 README 摘要（未伪造描述）。"
    )
    lines.append("")
    return lines


def _positioning_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    scale, structure = _section(card, "scale"), _section(card, "structure")
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    return [
        "## 1. 项目定位与目标",
        "",
        f"从仓库元数据看，{inputs.owner}/{inputs.repo} 属于 `{inputs.domain}` 领域、"
        f"`{inputs.channel}` 通道，主语言为 {_first_language(inputs)}，"
        f"当前约 {_whole(scale.get('stars'))} stars / {_whole(scale.get('forks'))} forks。",
        "",
        "项目阶段只能做**信号级判断**："
        f"仓库已存在 {_age(_section(card, 'identity').get('age_days'))}，"
        f"近一年发布 {_whole(scale.get('release_count_365d'))} 个版本，"
        f"最近提交距今 {_whole(_section(card, 'signals').get('days_since_commit'))} 天。"
        "这只能说明它是否还在维护，不能替代对 roadmap、竞品与真实用户群的判断。",
        "",
        f"入口文件：{', '.join(entrypoints) if entrypoints else '未识别'}。"
        "本次**未采集** roadmap、竞品对比、用户画像与商业模式；这些空白不应被读成“没有”。",
        "",
    ]


def _license_section(inputs: ReportInputs) -> list[str]:
    governance = _section(inputs.card, "governance")
    return [
        "## 2. 许可证与合规风险",
        "",
        f"主许可证为 **{_cell(as_str(governance.get('license')))}**，"
        f"组织类型为 {_cell(as_str(governance.get('org_type')))}，"
        f"治理文档：{'有' if governance.get('has_governance_docs') else '未检出'}。",
        "",
        "**当前无法回答但必须人工确认**：",
        "",
        "- 依赖链中是否存在 GPL/AGPL 等强传染许可证；",
        "- 模型权重、数据集、第三方素材的许可与商用限制；",
        "- 是否要求签署 CLA，以及贡献代码的版权归属。",
        "",
        "> 结论：许可证字段可用于初筛，但不能替代法务审查；本报告不给出“可商用”结论。",
        "",
    ]


def _insight_bullets(inputs: ReportInputs, limit: int | None = None) -> list[str]:
    if inputs.insight is None or not inputs.insight.items:
        return []
    items = inputs.insight.items[:limit] if limit else inputs.insight.items
    return [
        f"- 选择「{item.chose}」，放弃「{item.alternative}」，代价是「{item.cost}」"
        f"（证据 `{item.evidence}`）。"
        for item in items
    ]


def _architecture_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    structure, deps = _section(card, "structure"), _section(card, "deps")
    parallel, cache = _section(card, "parallel"), _section(card, "cache")
    modules = _rows(structure.get("top_modules"))[:5]
    module_text = "、".join(
        f"`{as_str(row.get('path'))}`（{_whole(row.get('files'))} 文件）" for row in modules
    )
    hits = []
    for label, section in (("并行", parallel), ("缓存", cache)):
        enabled = [as_str(key) for key, value in _section(section, "hits").items() if value]
        if enabled:
            hits.append(f"{label}轴 {', '.join(sorted(enabled))}")
    lines = [
        "## 3. 架构与模块",
        "",
        f"代码主体集中在：{module_text or '未识别 Top 模块'}；"
        f"最大目录深度 {_whole(structure.get('max_depth'))}，"
        f"monorepo：{'是' if structure.get('monorepo') else '否'}。",
        "",
        f"内部模块 import 边约 {_whole(deps.get('internal_edge_count'))} 条（依赖图见下）。"
        + (
            "检测到" + "；".join(hits) + "，具体证据见附录 B。"
            if hits
            else "未检测到并行/缓存轴证据。"
        ),
        "",
    ]
    bullets = _insight_bullets(inputs, limit=3)
    if bullets:
        lines.append("从代码证据看，最关键的几个取舍是：")
        lines.append("")
        lines.extend(bullets)
        lines.append("")
    lines.extend(
        [
            "```mermaid",
            depgraph_mermaid(_graph_dict(deps)),
            "```",
            "",
        ]
    )
    return lines


def _engineering_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    structure, sources = _section(card, "structure"), _section(card, "sources")
    hardware = _section(card, "hardware")
    lines = [
        "## 4. 运行与工程体系",
        "",
        f"仓库约 {_whole(structure.get('files'))} 个文件、"
        f"{_bytes(_int_or_none(structure.get('bytes')))}；"
        f"本次采集到 {len(_rows(sources.get('files')))} 个源码切片"
        f"（tarball `{as_str(sources.get('tarball_sha256'))[:16] or DASH}`）。",
        "",
        f"语言构成：{_languages(_section(card, 'lang').get('shares'))}。"
        f"硬件相关：vendors={_list(hardware.get('vendors'))}、"
        f"kernel_langs={_list(hardware.get('kernel_langs'))}。",
        "",
        "**本次未采集**：构建脚本、依赖安装、测试体系、CI/CD、配置与 secret 管理。"
        "因此本报告不能回答“能否在目标环境跑起来”，只能给结构线索。",
        "",
    ]
    limitations = [as_str(item) for item in card.get("limitations", []) if as_str(item)]
    if limitations:
        lines.append("**特征卡已知限制**：")
        lines.append("")
        lines.extend(f"- {item}" for item in limitations)
        lines.append("")
    return lines


def _maintenance_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    scale, signals = _section(card, "scale"), _section(card, "signals")
    contributors = _int_or_none(scale.get("contributors"))
    bus = _ratio(signals.get("bus_factor_top1_share"))
    risks: list[str] = []
    if isinstance(contributors, int) and contributors <= 2:
        risks.append("贡献者很少，存在 bus factor 风险")
    if bus != DASH:
        risks.append(f"Top1 贡献者占比 {bus}，集中度需关注")
    if _section(card, "governance").get("has_governance_docs") is not True:
        risks.append("未检出治理文档，贡献流程可能不透明")
    if inputs.external is None or inputs.external.status != "hit":
        risks.append("外部架构资料未命中，架构判断主要依赖本地代码")
    lines = [
        "## 5. 维护状态与风险",
        "",
        f"贡献者 {_whole(contributors)} 人，Top1 占比 {bus}；"
        f"近 90 天 / 365 天提交 {_whole(scale.get('commits_90d'))} / "
        f"{_whole(scale.get('commits_365d'))} 次；"
        f"最近提交距今 {_whole(signals.get('days_since_commit'))} 天，"
        f"维护状态「{_cell(as_str(signals.get('maintenance_state')))}」。",
        "",
        "**主要风险（基于现有信号）**：",
        "",
    ]
    lines.extend(
        f"- {item}"
        for item in (risks or ["未发现明显信号级风险；仍需人工复核 issue/PR 与版本策略。"])
    )
    lines.append("")
    return lines


def _extension_section(inputs: ReportInputs) -> list[str]:
    structure = _section(inputs.card, "structure")
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    modules = _rows(structure.get("top_modules"))[:5]
    lines = [
        "## 6. 扩展与二次开发",
        "",
        "本次**未识别到显式的插件/适配器注册机制**；这不等于没有，只说明当前采集粒度看不到。"
        "可优先人工检查以下位置：",
        "",
    ]
    candidates = entrypoints + [as_str(row.get("path")) for row in modules]
    lines.extend(f"- `{path}`" for path in dict.fromkeys(candidates) if path)
    if not candidates:
        lines.append("- 未获得可用入口/模块线索。")
    lines.extend(
        [
            "",
            "> 二次开发前建议先确认：扩展点、配置注入方式、测试与发布流程；本报告不替代实际试跑。",
            "",
        ]
    )
    return lines


def _metadata_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    identity = _section(card, "identity")
    decision = inputs.decision
    depth_cell = decision.actual
    if decision.downgraded:
        depth_cell = f"{decision.actual}（降级：{decision.reason_text}）"
    lines = [
        "## 运行元数据（附录 C）",
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
        "## 体检事实（确定性，零 LLM）（附录 E）",
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
        "## 特征卡摘要（附录 D）",
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
            "## 洞见（附录 A）",
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

    lines = ["## 洞见（附录 A）", "", DASH]
    if inputs.insight_reason:
        lines.extend(["", f"> fast 档未产出洞见：{inputs.insight_reason}"])
    lines.append("")
    return lines


def _external_section(inputs: ReportInputs) -> list[str]:
    probe = inputs.external
    if probe is None:
        return [
            "## 外部资料（附录 B）",
            "",
            "- DeepWiki / Zread：不可用（未索引）",
            "- 判定原因：本次未启用外部工具探测",
            "",
        ]

    lines = [
        "## 外部资料（附录 B）",
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
