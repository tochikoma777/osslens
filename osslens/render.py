"""报告渲染（Markdown，字节一致）。

结构写死为执行手册附录 A 的五个区块，顺序不可变：
运行元数据 → 体检事实 → 特征卡摘要 → 洞见（off 档填 `—`）→ 外部资料。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .collect import SourceNote
from .depth import DepthDecision
from .util import as_str, fmt_iso

DASH = "—"


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


def render_report(inputs: ReportInputs) -> str:
    lines: list[str] = []
    lines.append(f"# 开源项目分析 · {inputs.owner}/{inputs.repo}")
    lines.append("")
    lines.extend(_metadata_section(inputs))
    lines.extend(_facts_section(inputs))
    lines.extend(_featcard_section(inputs))
    lines.extend(_insight_section())
    lines.extend(_external_section(inputs))
    return "\n".join(lines).rstrip("\n") + "\n"


def _metadata_section(inputs: ReportInputs) -> list[str]:
    card = inputs.card
    identity = _section(card, "identity")
    decision = inputs.decision
    depth_cell = decision.actual
    if decision.downgraded:
        depth_cell = f"{decision.actual}（降级：{decision.reason_text}）"
    return (
        [
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
            "",
            "**档位决策链路**：",
            "",
        ]
        + [f"{index}. {step}" for index, step in enumerate(decision.chain, start=1)]
        + [
            "",
            "**上下文组装**（裁剪发生在调用之前）：",
            "",
            "| 块 | 优先级 | 估算 token |",
            "|---|---|---|",
            f"| featcard | 1 | {DASH} |",
            f"| readme | 2 | {DASH} |",
            f"| source_files | 4 | {DASH} |",
            "",
            f"- 丢弃：{DASH}（{decision.actual} 档不组装上下文，未发起任何模型请求）",
            f"- 合计 0 / 上限 {decision.prompt_token_limit}",
            "",
        ]
    )


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
    entrypoints = [as_str(item) for item in structure.get("entrypoints", []) if as_str(item)]
    deps = _section(card, "deps")
    max_depth = _whole(structure.get("max_depth"))
    monorepo = "是" if structure.get("monorepo") else "否"
    direct = _whole(deps.get("direct"))
    transitive = _whole(deps.get("transitive"))
    lines = [
        "## 特征卡摘要",
        "",
        f"- 卡文件：`{inputs.featcard_relpath}`（schema {as_str(card.get('schema_version'))}）",
        f"- 入口文件：{', '.join(entrypoints) if entrypoints else DASH}",
        f"- 最大目录深度：{max_depth}；monorepo：{monorepo}",
        f"- 依赖：直接 / 传递 = {direct} / {transitive}（L0 未解析清单文件）",
        f"- 并行轴 hits：{_hits(parallel.get('hits'))}",
        f"- 缓存 hits：{_hits(cache.get('hits'))}",
        f"- 硬件：vendors={_list(hardware.get('vendors'))}、"
        f"arch_gates={_list(hardware.get('arch_gates'))}、"
        f"kernel_langs={_list(hardware.get('kernel_langs'))}",
        f"- 治理文档：{'是' if _section(card, 'governance').get('has_governance_docs') else '否'}",
        "",
        "**已知限制**（L0 只跑元数据层，逐条可核验）：",
        "",
    ]
    limitations = [as_str(item) for item in card.get("limitations", []) if as_str(item)]
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append(f"- {DASH}")
    lines.append("")
    return lines


def _insight_section() -> list[str]:
    return ["## 洞见", "", DASH, ""]


def _external_section(inputs: ReportInputs) -> list[str]:
    return [
        "## 外部资料",
        "",
        "- DeepWiki / Zread：不可用（未索引）",
        f"- 判定原因：L0 未接线外部工具（L1 起启用 fail-closed 判定），"
        f"本次未发起任何探测请求；快照 sha256 `{inputs.snapshot_sha256}`",
        "",
    ]


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


def _hits(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return DASH
    return "、".join(f"{key}={value[key]}" for key in sorted(value))


def _list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "[]"
    return "[" + ", ".join(sorted(as_str(item) for item in value)) + "]"


__all__ = ["DASH", "ReportInputs", "render_report"]
