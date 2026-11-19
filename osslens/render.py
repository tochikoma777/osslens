"""报告渲染（Markdown，字节一致）。

v3 结构：导读 + 6 章（定位 / 架构 / 抽象 / ADR / 扩展 / 经验卡）+ 附录 A/B。
正文以叙述与判断为主，参数表、许可证、维护、工程细节下沉到附录；
确定性内容由代码生成，LLM 只提供带 file:line 证据的取舍、规则与边界。
模板与版本历史见 docs/报告模板-v3.md、docs/报告模板-版本记录.md。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
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

# v3 阅读档位：权重是「注意力预算」，不是硬性字数（见 docs/报告模板-v3.md）。
# 键顺序即为报告章节顺序；工程/维护默认进附录，选型尽调时提升为正文重点。
REPORT_PROFILES: dict[str, dict[str, int]] = {
    "architecture_learning": {
        "定位": 20,
        "架构": 30,
        "抽象": 15,
        "ADR": 20,
        "扩展": 5,
        "经验卡": 10,
        "工程维护": 0,
    },
    "adoption_due_diligence": {
        "定位": 15,
        "架构": 15,
        "抽象": 10,
        "ADR": 10,
        "扩展": 5,
        "经验卡": 0,
        "工程维护": 45,
    },
    "contributor_onboarding": {
        "定位": 10,
        "架构": 25,
        "抽象": 10,
        "ADR": 15,
        "扩展": 25,
        "经验卡": 5,
        "工程维护": 10,
    },
}
_PROFILE_LABELS = {
    "architecture_learning": "架构学习",
    "adoption_due_diligence": "选型尽调",
    "contributor_onboarding": "贡献入门",
}
_EVIDENCE_LEGEND = (
    "证据约定：[事实] 确定性提取 · [判断] 有 file:line 或文档锚点 · [未获得] 当前未采集"
)


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
    # v3：定位/架构所需的确定性材料（由 cli 从快照与源码切片提取）
    repo_meta: dict[str, Any] = field(default_factory=dict)
    readme: str = ""
    doc_excerpts: tuple[tuple[str, str], ...] = ()
    pattern_hits: tuple[tuple[str, str, int], ...] = ()
    profile: str = "architecture_learning"


def render_report(inputs: ReportInputs) -> str:
    lines: list[str] = []
    lines.append(f"# {inputs.owner}/{inputs.repo} 深度分析")
    lines.append("")
    lines.extend(cost_anomaly_block(inputs.cost))
    lines.extend(_profile_line(inputs))
    lines.extend(_lead_v3(inputs))
    lines.extend(_positioning_v3(inputs))
    lines.extend(_architecture_v3(inputs))
    lines.extend(_abstractions_v3(inputs))
    lines.extend(_adr_section(inputs))
    lines.extend(_extension_v3(inputs))
    lines.extend(_experience_section(inputs))
    lines.extend(_evidence_appendix(inputs))
    lines.extend(["## 附录 B 许可证 / 维护 / 工程 / 成本", ""])
    lines.extend(_license_section(inputs))
    lines.extend(_maintenance_section(inputs))
    lines.extend(_engineering_section(inputs))
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


def _profile_line(inputs: ReportInputs) -> list[str]:
    """报告头部的阅读档位与证据约定（v3）：让读者先知道该按什么权重读。"""
    profile = inputs.profile or "architecture_learning"
    label = _PROFILE_LABELS.get(profile, profile)
    weights = REPORT_PROFILES.get(profile, REPORT_PROFILES["architecture_learning"])
    budget = " / ".join(f"{name} {value}" for name, value in weights.items())
    return [
        f"> 阅读档位：{label}（profile={profile}）",
        f"> 注意力预算：{budget}",
        f"> {_EVIDENCE_LEGEND}",
        "",
    ]


def _risk_items(inputs: ReportInputs) -> list[str]:
    """基于现有信号的确定性风险清单；供导读与附录 B2 复用，避免两处口径漂移。"""
    card = inputs.card
    scale, signals = _section(card, "scale"), _section(card, "signals")
    governance = _section(card, "governance")
    risks: list[str] = []
    if inputs.repo_meta.get("archived") is True:
        risks.append("仓库已归档（archived=true），不再接收常规更新")
    contributors = _int_or_none(scale.get("contributors"))
    if contributors is not None and contributors <= 2:
        risks.append(f"贡献者仅 {contributors} 人，bus factor 风险高")
    bus = _ratio(signals.get("bus_factor_top1_share"))
    if bus != DASH:
        risks.append(f"Top1 贡献者占比 {bus}，决策集中度需关注")
    if governance.get("has_governance_docs") is not True:
        risks.append("未检出治理文档，贡献与决策流程可能不透明")
    if inputs.external is None or inputs.external.status != "hit":
        risks.append("外部架构资料未命中，架构判断主要依赖本地代码切片")
    return risks


def _audience_guess(inputs: ReportInputs) -> str:
    """从自述/README/topics 推断目标用户；推断不出就明确「未获得」。"""
    raw_topics = inputs.repo_meta.get("topics")
    topics = [as_str(item) for item in raw_topics] if isinstance(raw_topics, list) else []
    text = " ".join(
        [as_str(inputs.repo_meta.get("description")), inputs.readme[:2000], *topics]
    ).lower()
    guesses: list[str] = []
    if re.search(r"inference|serving|llm|gpu|cuda|kernel|quant", text):
        guesses.append("模型工程师 / 推理基础设施开发者")
    if re.search(r"sdk|library|framework|api|plugin", text):
        guesses.append("应用与平台开发者")
    if re.search(r"cli|command|tool|benchmark", text):
        guesses.append("终端用户与性能调优人员")
    if not guesses:
        return "[未获得] 现有材料不足以判断目标用户"
    return "[判断] " + "；".join(dict.fromkeys(guesses))


def _module_duty(path: str) -> str:
    """按目录名给出一句话职责（启发式，报告内标注为判断而非事实）。"""
    name = path.rstrip("/").rsplit("/", 1)[-1].lower()
    rules = (
        (("csrc", "kernel", "cuda"), "原生内核与算子实现"),
        (("src", "core"), "核心实现"),
        (("cli", "cmd", "entry"), "命令行/进程入口"),
        (("api", "server", "service"), "对外接口与服务层"),
        (("binding", "python", "py"), "语言绑定与封装"),
        (("test", "spec"), "测试与用例"),
        (("example", "demo", "bench"), "示例与基准"),
        (("doc",), "文档"),
        (("script", "tool"), "脚本与工具"),
    )
    for keys, duty in rules:
        if any(key in name for key in keys):
            return duty
    return "业务实现（职责需人工确认）"


def _lead_v3(inputs: ReportInputs) -> list[str]:
    """导读：是什么 / 架构一句话 / 最大风险 / 不适合谁（120–180 字）。"""
    card = inputs.card
    structure = _section(card, "structure")
    description = as_str(inputs.repo_meta.get("description")).strip()
    excerpt = _readme_excerpt(inputs)
    what = description or excerpt or "[未获得] 快照与 README 均未提供项目描述"
    modules = _rows(structure.get("top_modules"))[:3]
    names = "、".join(f"`{as_str(row.get('path'))}`" for row in modules)
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    arch = f"顶层以 {names} 为主" if names else "[未获得] 未识别顶层模块"
    if entrypoints:
        arch += f"，入口为 `{entrypoints[0]}`"
    arch += "（静态结构判断，未做动态跟踪）。"
    risks = _risk_items(inputs)
    risk = risks[0] if risks else "未发现明显信号级风险；仍需人工复核"
    return [
        "## 导读",
        "",
        f"> **是什么**：{what}",
        f"> **架构一句话**：[判断] {arch}",
        f"> **最大风险**：{risk}",
        "> **不适合**：需要稳定 API/长期支持承诺的场景，请先核对发布节奏与维护状态；"
        "依赖链许可证与权重许可能力当前未采集，不能据此做出商用结论。",
        "",
    ]


def _positioning_v3(inputs: ReportInputs) -> list[str]:
    """第 1 章：解决什么问题、目标用户、替代方案、阶段。"""
    card = inputs.card
    scale, signals = _section(card, "scale"), _section(card, "signals")
    identity = _section(card, "identity")
    description = as_str(inputs.repo_meta.get("description")).strip()
    excerpt = _readme_excerpt(inputs)
    lines = [
        "## 1. 项目定位与目标",
        "",
        f"[事实] {inputs.owner}/{inputs.repo} 属于 `{inputs.domain}` 领域、"
        f"`{inputs.channel}` 通道，主语言 {_first_language(inputs)}，"
        f"{_whole(scale.get('stars'))} stars / {_whole(scale.get('forks'))} forks。",
        "",
        f"[事实] 项目自述：{description or '[未获得] 快照未提供 description'}。",
        "",
        f"[事实] README 摘要：{excerpt or '[未获得] 本次未获得可用 README 文本'}。",
        "",
    ]
    lines.extend(
        [
            f"- **目标用户**：{_audience_guess(inputs)}",
            "- **替代方案与差异**：[未获得] 本次未采集竞品对比与 roadmap，"
            "不得据此推断「没有替代品」。",
            "- **不解决什么**：[未获得] 没有路线图与 issue 语料，无法可靠界定能力边界。",
        ]
    )
    lines.extend(
        [
            "",
            f"[判断] 阶段信号：仓库已存在 {_age(identity.get('age_days'))}，"
            f"近一年发布 {_whole(scale.get('release_count_365d'))} 个版本，"
            f"最近提交距今 {_whole(signals.get('days_since_commit'))} 天，"
            f"维护状态「{_cell(as_str(signals.get('maintenance_state')))}」。"
            "这只说明是否仍在维护，不等于成熟度结论。",
            "",
        ]
    )
    return lines


def _architecture_v3(inputs: ReportInputs) -> list[str]:
    """第 2 章：上下文边界、模块职责、运行时链路、数据/控制流。"""
    card = inputs.card
    structure, deps = _section(card, "structure"), _section(card, "deps")
    parallel, cache = _section(card, "parallel"), _section(card, "cache")
    hardware = _section(card, "hardware")
    modules = _rows(structure.get("top_modules"))[:5]
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    doc_paths = [path for path, _ in inputs.doc_excerpts]
    arch_docs = [
        path for path in doc_paths if re.search(r"arch|design|overview|readme", path, re.I)
    ]
    lines = [
        "## 2. 架构全景",
        "",
        "### 2.1 上下文边界",
        "",
        f"[判断] 架构说明文档：{', '.join(f'`{path}`' for path in arch_docs) or '[未获得]'}"
        "；边界结论来自文档与目录结构，未经运行验证。",
        f"[事实] 硬件/内核线索：vendors={_list(hardware.get('vendors'))}、"
        f"kernel_langs={_list(hardware.get('kernel_langs'))}。",
        "",
        "### 2.2 模块职责",
        "",
    ]
    if modules:
        lines.extend(["| 模块 | 文件数 | 职责（启发式） |", "|---|---:|---|"])
        lines.extend(
            f"| `{as_str(row.get('path'))}` | {_whole(row.get('files'))} | "
            f"{_module_duty(as_str(row.get('path')))} |"
            for row in modules
        )
    else:
        lines.append("[未获得] 未识别 Top 模块（快照可能被截断）。")
    lines.extend(
        [
            "",
            "### 2.3 一次调用的路径（运行时视图）",
            "",
            f"[判断] 静态推断：{', '.join(f'`{item}`' for item in entrypoints) or '入口未识别'}"
            f" → 调度/核心模块（见上表） → 输出。"
            f"内部 import 边约 {_whole(deps.get('internal_edge_count'))} 条，"
            "可作为调用方向的粗线索；**未做运行时跟踪**，具体分支需读源码确认。",
            "",
            "### 2.4 数据与控制流",
            "",
        ]
    )
    axis_lines: list[str] = []
    for label, section in (("并行", parallel), ("缓存", cache)):
        enabled = [as_str(key) for key, value in _section(section, "hits").items() if value]
        if enabled:
            axis_lines.append(f"{label}轴命中 {', '.join(sorted(enabled))}")
    if axis_lines:
        lines.append("[事实] " + "；".join(axis_lines) + "（证据见附录 A）。")
    else:
        lines.append("[未获得] 未检测到并行/缓存轴证据；不代表项目中不存在。")
    lines.extend(["", "```mermaid", depgraph_mermaid(_graph_dict(deps)), "```", ""])
    return lines


def _abstractions_v3(inputs: ReportInputs) -> list[str]:
    """第 3 章：核心接口/基类/注册机制；没有证据就明确写未获得。"""
    card = inputs.card
    structure = _section(card, "structure")
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    lines = ["## 3. 核心抽象与契约", ""]
    if inputs.pattern_hits:
        lines.extend(
            [
                "[事实] 源码切片中命中以下模式（正则扫描，仅代表本次切片）：",
                "",
                "| 模式 | 位置 | 说明 |",
                "|---|---|---|",
            ]
        )
        for pattern, path, line in inputs.pattern_hits[:10]:
            lines.append(f"| `{pattern}` | `{path}:{line}` | 候选扩展/契约点 |")
        lines.extend(
            [
                "",
                "[判断] 这些命中说明项目存在注册/适配/分派结构，但**未做 AST 分析**，"
                "无法确认继承关系与调用契约的完整性。",
            ]
        )
    else:
        lines.append(
            "[未获得] 本次源码切片未识别到显式接口/注册模式；这不等于项目没有抽象层，"
            "只说明当前采集粒度不足。"
        )
    if entrypoints:
        lines.extend(
            [
                "",
                "入口候选（可作为契约阅读起点）：" + "、".join(f"`{item}`" for item in entrypoints),
            ]
        )
    lines.append("")
    return lines


def _adr_section(inputs: ReportInputs) -> list[str]:
    """第 4 章：ADR 六字段；条目来自 LLM 洞见，证据必须是 file:line。"""
    lines = ["## 4. 关键设计决策（ADR）", ""]
    items = list(inputs.insight.items) if inputs.insight is not None else []
    if not items:
        reason = inputs.insight_reason or "本次未产出带证据的取舍"
        lines.extend(
            [
                f"[未获得] {reason}；ADR 至少 3 条的要求未满足，不用通用判断填充。",
                "",
            ]
        )
        return lines
    lines.extend(
        [
            "每条固定六字段：决策 / 替代 / 代价 / 证据 / 可复用规则 / 边界·反模式。",
            "",
        ]
    )
    for index, item in enumerate(items[:6], start=1):
        rule = item.rule or "[未获得] 模型未给出可迁移规则，需人工补"
        boundary = item.boundary or "[未获得] 未给出适用边界"
        lines.extend(
            [
                f"### ADR-{index} · {item.id}: {item.chose}",
                "",
                f"- **决策**：{item.chose}",
                f"- **替代**：{item.alternative}",
                f"- **代价**：{item.cost}",
                f"- **证据**：`{item.evidence}`",
                f"- **可复用规则**：{rule}",
                f"- **边界/反模式**：{boundary}",
                "",
            ]
        )
    if len(items) < 3:
        lines.extend(
            [
                f"> 本次仅 {len(items)} 条：证据不足，未补足到 3 条；"
                "缺口在源码文档（架构说明、roadmap）与运行时数据。",
                "",
            ]
        )
    return lines


def _extension_v3(inputs: ReportInputs) -> list[str]:
    """第 5 章：扩展点与改造成本。"""
    card = inputs.card
    structure = _section(card, "structure")
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    modules = _rows(structure.get("top_modules"))[:5]
    ext_docs = [
        path
        for path, _ in inputs.doc_excerpts
        if re.search(r"contribut|extend|plugin|developer|hacking", path, re.I)
    ]
    lines = ["## 5. 扩展与改造路径", ""]
    if inputs.pattern_hits:
        lines.append("[事实] 可扩展点候选（与第 3 章同源）：")
        lines.append("")
        lines.extend(
            f"- `{path}:{line}` → {pattern}" for pattern, path, line in inputs.pattern_hits[:6]
        )
        lines.append("")
    else:
        lines.extend(["[未获得] 未识别到显式插件/注册点。", ""])
    candidates = entrypoints + [as_str(row.get("path")) for row in modules]
    lines.extend(
        [
            "[判断] 新增能力的静态路径（需按实际代码复核）：",
            "",
            "1. 在入口处接入参数/配置（入口候选："
            + (", ".join(f"`{path}`" for path in dict.fromkeys(candidates)) or "[未获得]")
            + "）；",
            "2. 复用上表中的注册/分派结构，实现新的后端或适配器；",
            "3. 补对应测试与文档，再走发布流程。",
            "",
            f"- 扩展文档：{', '.join(f'`{path}`' for path in ext_docs) or '[未获得]'}",
            "- 改造成本：[未获得] 需要先确认契约稳定性与测试覆盖，本报告不估算人日。",
            "",
        ]
    )
    return lines


def _experience_section(inputs: ReportInputs) -> list[str]:
    """第 6 章：经验卡（ADR 的二次抽象，必须有适用边界）。"""
    lines = ["## 6. 经验卡", ""]
    items = list(inputs.insight.items) if inputs.insight is not None else []
    cards = [item for item in items if item.rule]
    if not cards:
        lines.extend(
            [
                "[未获得] 本次没有带「可迁移规则」的条目（模型未输出 rule，或命中旧缓存）；"
                "经验卡留空，不用「要注重解耦」这类通用建议充数。",
                "",
            ]
        )
        return lines
    for index, item in enumerate(cards[:5], start=1):
        lines.extend(
            [
                f"### 经验 {index} · {item.rule}",
                "",
                f"- **证据**：`{item.evidence}`（来自 {inputs.owner}/{inputs.repo}）",
                f"- **适用边界**：{item.boundary or '[未获得]'}",
                f"- **反模式**：在边界之外照搬「{item.chose}」，代价会变成「{item.cost}」",
                "- **如果我来做**：先确认边界成立，再选择"
                f"「{item.chose}」而非「{item.alternative}」",
                "",
            ]
        )
    return lines


def _evidence_appendix(inputs: ReportInputs) -> list[str]:
    """附录 A：代码证据索引、外部资料、未知项（正文判断的出处都在这）。"""
    lines = ["## 附录 A 证据索引与未知项", "", "### A1. 代码证据索引", ""]
    insight = inputs.insight
    items = list(insight.items) if insight is not None else []
    if insight is not None and items:
        lines.extend(["| id | 决策 | 证据 |", "|---|---|---|"])
        lines.extend(f"| {item.id} | {item.chose} | `{item.evidence}` |" for item in items)
        lines.extend(["", f"- 置信度：{insight.confidence}"])
        if insight.paradigm_tags:
            tags = "、".join(insight.paradigm_tags)
            lines.append(f"- 架构范式标签：{tags}")
        if insight.dropped:
            lines.append(f"- 被代码丢弃的条目：{len(insight.dropped)} 条")
            lines.extend(f"  - {reason}" for reason in insight.dropped)
    else:
        lines.extend(
            [
                DASH,
                "",
                f"> 未产出洞见：{inputs.insight_reason or 'off 档不发起模型请求'}",
            ]
        )
    for pattern, path, line in inputs.pattern_hits:
        lines.append(f"- 模式 `{pattern}`：`{path}:{line}`")
    lines.append("")
    lines.extend(_external_section(inputs))
    lines.extend(["### A3. 未获得项", ""])
    lines.extend(
        [
            "- 依赖链许可证、模型权重/数据许可、CLA —— 未采集；",
            "- issue/PR 响应质量、CI 运行结果 —— 未采集；",
            "- roadmap、竞品对比、用户画像 —— 未采集；",
        ]
    )
    lines.extend(_degraded_lines(inputs.snapshot_notes))
    lines.append("")
    return lines


def _license_section(inputs: ReportInputs) -> list[str]:
    """附录 B1：许可证与合规风险（只给字段级初筛，不做法务结论）。"""
    governance = _section(inputs.card, "governance")
    return [
        "### B1. 许可证与合规风险",
        "",
        f"[事实] 主许可证 **{_cell(as_str(governance.get('license')))}**；"
        f"组织类型 {_cell(as_str(governance.get('org_type')))}；"
        f"治理文档：{'有' if governance.get('has_governance_docs') else '未检出'}。",
        "",
        "[未获得] 依赖链是否存在 GPL/AGPL、模型权重与数据集许可、CLA 要求；"
        "这些必须人工或由后续数据源补齐，本报告不给出「可商用」结论。",
        "",
    ]


def _maintenance_section(inputs: ReportInputs) -> list[str]:
    """附录 B2：维护状态与风险（信号级，与导读共用 _risk_items）。"""
    card = inputs.card
    scale, signals = _section(card, "scale"), _section(card, "signals")
    contributors = _int_or_none(scale.get("contributors"))
    bus = _ratio(signals.get("bus_factor_top1_share"))
    risks = _risk_items(inputs)
    lines = [
        "### B2. 维护状态与风险",
        "",
        f"[事实] 贡献者 {_whole(contributors)} 人，Top1 占比 {bus}；"
        f"近 90 天 / 365 天提交 {_whole(scale.get('commits_90d'))} / "
        f"{_whole(scale.get('commits_365d'))} 次；"
        f"最近提交距今 {_whole(signals.get('days_since_commit'))} 天，"
        f"维护状态「{_cell(as_str(signals.get('maintenance_state')))}」。",
        "",
    ]
    if risks:
        lines.extend(f"- {item}" for item in risks)
    else:
        lines.append("- 未发现信号级风险；issue/PR 质量与版本策略仍需人工复核。")
    lines.append("")
    return lines


def _engineering_section(inputs: ReportInputs) -> list[str]:
    """附录 B3：运行与工程体系（当前只到结构线索，构建/CI 未采集）。"""
    card = inputs.card
    structure, sources = _section(card, "structure"), _section(card, "sources")
    hardware = _section(card, "hardware")
    lines = [
        "### B3. 运行与工程体系",
        "",
        f"[事实] 仓库约 {_whole(structure.get('files'))} 个文件、"
        f"{_bytes(_int_or_none(structure.get('bytes')))}；"
        f"本次采集 {len(_rows(sources.get('files')))} 个源码切片"
        f"（tarball `{as_str(sources.get('tarball_sha256'))[:16] or DASH}`）。",
        f"[事实] 语言构成：{_languages(_section(card, 'lang').get('shares'))}；"
        f"硬件 vendors={_list(hardware.get('vendors'))}、"
        f"kernel_langs={_list(hardware.get('kernel_langs'))}。",
        "",
        "[未获得] 构建脚本、依赖安装、测试体系、CI/CD、配置与 secret 管理未采集；"
        "本报告不能回答「能否在目标环境跑起来」。",
        "",
    ]
    limitations = [as_str(item) for item in card.get("limitations", []) if as_str(item)]
    if limitations:
        lines.append("**特征卡已知限制**：")
        lines.append("")
        lines.extend(f"- {item}" for item in limitations)
        lines.append("")
    return lines


def _metadata_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    identity = _section(card, "identity")
    decision = inputs.decision
    depth_cell = decision.actual
    if decision.downgraded:
        depth_cell = f"{decision.actual}（降级：{decision.reason_text}）"
    lines = [
        "### B4. 运行元数据与成本",
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
        "### B6. 体检事实（确定性，零 LLM）",
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
        "### B5. 特征卡摘要",
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


def _external_section(inputs: ReportInputs) -> list[str]:
    probe = inputs.external
    if probe is None:
        return [
            "### A2. 外部资料",
            "",
            "- DeepWiki / Zread：不可用（未索引）",
            "- 判定原因：本次未启用外部工具探测",
            "",
        ]

    lines = [
        "### A2. 外部资料",
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
