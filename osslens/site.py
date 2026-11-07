"""L4 静态只读站点：MD + JSON 真源 → 确定性 HTML/MD。

★ 零后端 / 零 LLM / 零网络：本模块不导入 httpx、不构造任何 HTTP 客户端、不含模型端点字面量。
★ 真源只读：只读 reports / featcards / patterns / costs / runs；产物**只写 site/**。
★ 幂等：所有集合排序后输出；时间只来自 `--as-of` 或输入真源派生，绝不取运行时钟；
  不含绝对路径、不含运行时间戳。
★ 空态诚实：规律库为空时显式说明，绝不生成示例条目。
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config, Layout
from .depth import load_events, summarize
from .patterns import PatternEntry, code_evidence_from_card, load_library
from .render import D10_WORDING
from .util import (
    UsageError,
    as_dict,
    as_int,
    as_list,
    as_str,
    atomic_write_text,
    fmt_iso,
    parse_iso,
    read_jsonl,
)

SITE_DIRNAME = "site"
REPORT_SECTIONS = ("运行元数据", "体检事实", "特征卡摘要", "洞见", "外部资料")
PRICE_SOURCE_NOTE = "单价只来自 config.yaml → llm.price_table（代码不内置任何价格字面量）"


# --------------------------------------------------------------------------- 时间


def resolve_site_as_of(layout: Layout, raw: str | None) -> datetime:
    """时间只来自 `--as-of` 或输入真源（特征卡 analyzed_at / 报告文件名日期）。"""
    if raw:
        try:
            return parse_iso(raw)
        except ValueError as exc:
            raise UsageError(f"--as-of 不是合法 ISO8601：{raw!r}") from exc
    stamps: list[datetime] = []
    for path in sorted(layout.featcards_dir.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        stamp = as_str(as_dict(card.get("identity")).get("analyzed_at"))
        if stamp:
            try:
                stamps.append(parse_iso(stamp))
            except ValueError:
                continue
    for path in sorted(layout.reports_dir.glob("*.md")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})\.md$", path.name)
        if match:
            try:
                stamps.append(parse_iso(f"{match.group(1)}T00:00:00Z"))
            except ValueError:
                continue
    if stamps:
        return max(stamps)
    raise UsageError("工作区无报告/特征卡且未传 --as-of：无法确定基准时间（时间不取运行时钟）")


# --------------------------------------------------------------------------- 真源读取（只读）


@dataclass(frozen=True)
class ReportDoc:
    stem: str
    repo: str
    as_of: str
    depth: str
    price_line: str
    cost_line: str
    text: str


@dataclass(frozen=True)
class FeatcardDoc:
    repo: str
    commit: str
    analyzed_at: str
    channel: str
    stars: int
    evidence: tuple[str, ...]


def _meta_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        rows[cells[0].replace("**", "").strip()] = cells[1]
    return rows


def load_reports(layout: Layout) -> tuple[ReportDoc, ...]:
    docs: list[ReportDoc] = []
    for path in sorted(layout.reports_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta = _meta_rows(text)
        docs.append(
            ReportDoc(
                stem=path.stem,
                repo=meta.get("仓库", path.stem),
                as_of=meta.get("分析基准时间 (as-of)", ""),
                depth=meta.get("实际档位 (actual_depth)", "—"),
                price_line=meta.get("单价", ""),
                cost_line=meta.get("成本说明", ""),
                text=text,
            )
        )
    return tuple(sorted(docs, key=lambda item: (item.repo, item.as_of, item.stem)))


def load_featcards(layout: Layout) -> tuple[FeatcardDoc, ...]:
    docs: list[FeatcardDoc] = []
    for path in sorted(layout.featcards_dir.glob("*.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(card, dict):
            continue
        identity = as_dict(card.get("identity"))
        repo = as_str(identity.get("repo"), path.stem)
        evidence = tuple(
            sorted({item.path for item in code_evidence_from_card(card, repo) if item.path})
        )
        docs.append(
            FeatcardDoc(
                repo=repo,
                commit=as_str(identity.get("commit")),
                analyzed_at=as_str(identity.get("analyzed_at")),
                channel=as_str(identity.get("channel")),
                stars=as_int(as_dict(card.get("scale")).get("stars")),
                evidence=evidence,
            )
        )
    return tuple(sorted(docs, key=lambda item: (item.repo, item.commit)))


# --------------------------------------------------------------------------- 空态


def empty_patterns_note(config: Config, runs: Sequence[Mapping[str, Any]]) -> str:
    """规律库为空时的诚实说明；数字全部来自 config 与 run 记录，不硬编码。"""
    threshold = config.abstract.cluster_min_new_projects
    target: Mapping[str, Any] | None = None
    for row in runs:
        if as_str(row.get("status")) == "insufficient_samples":
            target = row
    if target is None:
        return "规律库尚无条目（未获得 run 记录：无法确认首次真实抽象状态）"
    cluster = as_str(target.get("cluster"))
    trigger = as_str(target.get("trigger"))
    match = re.search(r"新增样本\s*(\d+)", trigger)
    count = int(match.group(1)) if match else 0
    return f"规律库尚无条目（首次真实抽象未触发：{cluster} 簇 {count} < {threshold}）"


# --------------------------------------------------------------------------- 极简 MD→HTML


_RAW_PREFIX = "\x00raw:"


def _raw(content: str) -> str:
    """标记站点自身生成的可信 HTML（链接 / 列表），避免被 _inline 二次转义。"""
    return _RAW_PREFIX + content


def _inline(raw: str) -> str:
    if raw.startswith(_RAW_PREFIX):
        return raw[len(_RAW_PREFIX) :]
    escaped = html.escape(raw, quote=False)
    with_bold = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", with_bold)


def md_to_html(text: str) -> str:
    """只处理报告实际用到的构造，保持五区块顺序；不做任何外部依赖或脚本。"""
    lines = text.splitlines()
    out: list[str] = []
    index = 0
    total = len(lines)
    while index < total:
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            index += 1
            buffer: list[str] = []
            while index < total and not lines[index].strip().startswith("```"):
                buffer.append(lines[index])
                index += 1
            index += 1
            cls = f' class="language-{html.escape(language)}"' if language else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(buffer))}</code></pre>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if (
            stripped.startswith("|")
            and index + 1 < total
            and re.fullmatch(r"\|[\s:|-]+\|", lines[index + 1].strip())
        ):
            header = [cell.strip() for cell in stripped.strip("|").split("|")]
            index += 2
            body: list[list[str]] = []
            while index < total and lines[index].strip().startswith("|"):
                body.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            thead = "".join(f"<th>{_inline(cell)}</th>" for cell in header)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
                for row in body
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue
        ordered = bool(re.match(r"^\d+\.\s+", stripped))
        if ordered or re.match(r"^[-*]\s+", stripped):
            items: list[str] = []
            while index < total:
                candidate = lines[index].strip()
                pattern = r"^\d+\.\s+(.*)$" if ordered else r"^[-*]\s+(.*)$"
                item = re.match(pattern, candidate)
                if not item:
                    break
                items.append(f"<li>{_inline(item.group(1))}</li>")
                index += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            out.append("<hr>")
            index += 1
            continue
        paragraph = [stripped]
        index += 1
        while index < total:
            candidate = lines[index].strip()
            if (
                not candidate
                or candidate.startswith("|")
                or candidate.startswith("```")
                or re.match(r"^#{1,6}\s", candidate)
                or re.match(r"^[-*]\s+", candidate)
                or re.match(r"^\d+\.\s+", candidate)
            ):
                break
            paragraph.append(candidate)
            index += 1
        out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
    return "\n".join(out)


# --------------------------------------------------------------------------- 页面骨架


_CSS = (
    "body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;margin:0;color:#1b1f23;"
    "background:#fff;line-height:1.6}"
    "header,main,footer{max-width:960px;margin:0 auto;padding:16px 24px}"
    "header{border-bottom:1px solid #e1e4e8}footer{border-top:1px solid #e1e4e8;color:#586069;"
    "font-size:.85em;margin-top:32px}"
    "nav a{margin-right:12px;color:#0366d6;text-decoration:none}"
    "h1,h2,h3{line-height:1.25}table{border-collapse:collapse;width:100%;margin:12px 0}"
    "th,td{border:1px solid #dfe2e5;padding:6px 10px;text-align:left;vertical-align:top}"
    "th{background:#f6f8fa}pre{background:#f6f8fa;padding:12px;overflow:auto}"
    "code{background:#f3f4f6;padding:1px 4px;border-radius:3px}"
    "pre code{background:none;padding:0}"
    ".empty,.note{background:#fff8e5;border-left:4px solid #d9a400;padding:10px 14px;margin:12px 0}"
    "ul,ol{padding-left:24px}"
)

_NAV_ITEMS = (
    ("首页", "index.html"),
    ("报告", "reports.html"),
    ("特征卡", "featcards.html"),
    ("规律库", "patterns.html"),
    ("成本", "costs.html"),
    ("抽象 run", "runs.html"),
    ("索引(MD)", "index.md"),
)


def _page(title: str, body: str) -> str:
    nav = " · ".join(f'<a href="{url}">{html.escape(label)}</a>' for label, url in _NAV_ITEMS)
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{html.escape(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        f"<header><h1>{html.escape(title)}</h1><nav>{nav}</nav></header>\n"
        f"<main>\n{body}\n</main>\n"
        "<footer>osslens 静态只读站点 · 无后端 / 无外部 JS 与 CDN / 零 LLM / 零网络</footer>\n"
        "</body></html>\n"
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


# --------------------------------------------------------------------------- 四块 + 索引


@dataclass(frozen=True)
class SitePlan:
    files: dict[str, str]
    as_of: str
    report_count: int
    featcard_count: int
    pattern_count: int
    run_count: int
    empty_note: str


def _render_index_md(
    *,
    as_of: str,
    reports: Sequence[ReportDoc],
    featcards: Sequence[FeatcardDoc],
    pattern_count: int,
    empty_note: str,
    run_rows: Sequence[Sequence[str]],
) -> str:
    lines = [
        "# osslens 静态站点索引",
        "",
        f"- 基准时间 (as-of)：{as_of}",
        "- 产物：纯静态 HTML/MD；无后端、无外部 JS/CDN、零 LLM、零网络",
        "- 真源：`reports/*.md` · `data/featcards/` · `patterns/library.yaml` · "
        "`data/costs/costs.jsonl` · `data/abstract/runs.jsonl`（站点只读）",
        "",
        "## 页面",
        "",
        *[f"- [{label}]({url})" for label, url in _NAV_ITEMS if url != "index.md"],
        "- [本索引（纯 MD，可脱离站点阅读）](index.md)",
        "",
        "## 项目清单（按仓库 / 基准时间 / 档位确定性排序）",
        "",
    ]
    if reports:
        lines.extend(
            [
                "| 仓库 | 基准时间 (as-of) | 实际档位 | 报告 |",
                "|---|---|---|---|",
            ]
        )
        for doc in reports:
            lines.append(
                f"| {doc.repo} | {doc.as_of or '—'} | {doc.depth} | "
                f"[报告页](report-{doc.stem}.html) · [源 MD](../reports/{doc.stem}.md) |"
            )
    else:
        lines.append("暂无报告（空态，不伪造内容）。")
    lines.extend(["", "## 特征卡", ""])
    if featcards:
        lines.extend(["| 仓库 | commit | 通道 | 代码证据条数 |", "|---|---|---|---|"])
        for card in featcards:
            lines.append(
                f"| {card.repo} | `{card.commit[:12] or '—'}` | {card.channel or '—'} | "
                f"{len(card.evidence)} |"
            )
    else:
        lines.append("暂无特征卡（空态，不伪造内容）。")
    lines.extend(["", "## 规律库", ""])
    if pattern_count:
        lines.append(f"共 {pattern_count} 条，见 [规律库页](patterns.html)。")
    else:
        lines.append(f"**{empty_note}**")
    lines.extend(["", "## 抽象 run 记录", ""])
    if run_rows:
        lines.extend(
            ["| run_id | 类型 | 簇 | 状态 | LLM 调用 |", "|---|---|---|---|---|"]
            + [f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |" for row in run_rows]
        )
    else:
        lines.append("暂无 run 记录（空态，不伪造内容）。")
    lines.append("")
    return "\n".join(lines)


def _render_index_html(
    *,
    as_of: str,
    report_count: int,
    featcard_count: int,
    pattern_count: int,
    run_count: int,
    empty_note: str,
) -> str:
    body = "\n".join(
        [
            f"<p>基准时间 (as-of)：<code>{html.escape(as_of)}</code>。"
            "时间只来自 <code>--as-of</code> 或输入真源，不含运行时钟。</p>",
            _table(
                ("区块", "条目数", "说明"),
                (
                    (_raw('<a href="reports.html">报告</a>'), str(report_count), "五区块顺序不变"),
                    (
                        _raw('<a href="featcards.html">特征卡</a>'),
                        str(featcard_count),
                        "含 file:line 证据",
                    ),
                    (_raw('<a href="patterns.html">规律库</a>'), str(pattern_count), "只读真源"),
                    (_raw('<a href="costs.html">成本</a>'), "—", "D10 口径 / 全局台账"),
                    (_raw('<a href="runs.html">抽象 run</a>'), str(run_count), "run 记录九字段"),
                ),
            ),
            f'<div class="empty">{html.escape(empty_note)}</div>'
            if pattern_count == 0
            else "<p>规律库已有条目，见规律库页。</p>",
            '<p class="note">站点为只读静态产物，可丢弃、可重建；不改写任何真源。</p>',
        ]
    )
    return _page("osslens · 静态只读站点", body)


def _render_reports(reports: Sequence[ReportDoc]) -> tuple[str, dict[str, str]]:
    rows = [
        (
            doc.repo,
            doc.as_of or "—",
            doc.depth,
            _raw(f'<a href="report-{doc.stem}.html">查看</a>'),
        )
        for doc in reports
    ]
    listing = _page(
        "报告",
        _table(("仓库", "基准时间 (as-of)", "实际档位", "链接"), rows)
        if rows
        else '<p class="empty">暂无报告（空态，不伪造内容）。</p>',
    )
    pages = {
        f"report-{doc.stem}.html": _page(
            f"报告 · {doc.repo}",
            f'<p class="note">源 MD：<code>../reports/{html.escape(doc.stem)}.md</code>；'
            "下方五区块顺序固定不变。</p>\n" + md_to_html(doc.text),
        )
        for doc in reports
    }
    return listing, pages


def _render_featcards(cards: Sequence[FeatcardDoc]) -> str:
    rows: list[Sequence[str]] = []
    for card in cards:
        evidence = (
            "<ul>"
            + "".join(f"<li><code>{html.escape(path)}</code></li>" for path in card.evidence)
            + "</ul>"
            if card.evidence
            else "—（该特征卡未采集源码证据）"
        )
        rows.append(
            (
                card.repo,
                _raw(f"<code>{html.escape(card.commit[:12] or '—')}</code>"),
                card.analyzed_at or "—",
                card.channel or "—",
                str(card.stars),
                _raw(evidence) if card.evidence else "—（该特征卡未采集源码证据）",
            )
        )
    body = _table(("仓库", "commit", "analyzed_at", "通道", "stars", "代码证据 file:line"), rows)
    return _page(
        "特征卡",
        body if rows else '<p class="empty">暂无特征卡（空态，不伪造内容）。</p>',
    )


def _render_patterns(entries: Sequence[PatternEntry], empty_note: str) -> str:
    if not entries:
        return _page(
            "规律库",
            f'<div class="empty"><strong>{html.escape(empty_note)}</strong></div>'
            "<p>真源 <code>patterns/library.yaml</code> 为 <code>[]</code>；"
            "按 S4 不用合成条目充数，本块保留且如实展示。</p>",
        )
    rows: list[Sequence[str]] = []
    for entry in sorted(entries, key=lambda item: item.id):
        pros = ", ".join(f"{item.repo} {item.path}" for item in entry.evidence if item.path)
        cons = ", ".join(item.repo for item in entry.counterexamples)
        rows.append(
            (
                entry.id,
                entry.level,
                entry.cluster,
                entry.statement,
                entry.status,
                pros or "—",
                cons or "—",
                str(entry.revision),
            )
        )
    return _page(
        "规律库",
        _table(("id", "层", "簇", "陈述", "状态", "正例", "反例", "revision"), rows),
    )


def _render_runs(
    runs: Sequence[Mapping[str, Any]], empty_note: str
) -> tuple[str, list[Sequence[str]]]:
    rows: list[Sequence[str]] = []
    for run in runs:
        rows.append(
            (
                as_str(run.get("run_id")),
                as_str(run.get("type")),
                as_str(run.get("cluster")),
                as_str(run.get("status")),
                str(as_int(run.get("llm_calls"))),
            )
        )
    rows.sort(key=lambda row: (row[0], row[1]))
    details: list[str] = []
    for run in sorted(runs, key=lambda item: as_str(item.get("run_id"))):
        warnings = [as_str(item) for item in as_list(run.get("warnings"))]
        details.append(
            "<h3>"
            + html.escape(as_str(run.get("run_id")))
            + " · "
            + html.escape(as_str(run.get("status")))
            + "</h3>"
            + _table(
                ("字段", "值"),
                (
                    ("type", as_str(run.get("type"))),
                    ("cluster", as_str(run.get("cluster"))),
                    ("trigger", as_str(run.get("trigger"))),
                    ("created_at", as_str(run.get("created_at"))),
                    ("llm_calls", str(as_int(run.get("llm_calls")))),
                    (
                        "produced_patterns",
                        ", ".join(as_str(item) for item in as_list(run.get("produced_patterns")))
                        or "—",
                    ),
                    (
                        "input_projects",
                        ", ".join(as_str(item) for item in as_list(run.get("input_projects")))
                        or "—",
                    ),
                    (
                        "self_check",
                        _raw(
                            "<code>"
                            + html.escape(
                                json.dumps(
                                    as_dict(run.get("self_check")),
                                    ensure_ascii=False,
                                    sort_keys=True,
                                )
                            )
                            + "</code>"
                        ),
                    ),
                    ("warnings", _raw("<br>".join(html.escape(item) for item in warnings) or "—")),
                ),
            )
        )
    body = (
        _table(("run_id", "type", "cluster", "status", "LLM 调用"), rows)
        if rows
        else ('<p class="empty">暂无 run 记录（空态，不伪造内容）。</p>')
    )
    if any(as_str(run.get("status")) == "insufficient_samples" for run in runs):
        body += f'<div class="empty">{html.escape(empty_note)}</div>'
    body += "\n".join(details)
    return _page("抽象 run 记录", body), rows


def _render_costs(
    config: Config,
    *,
    as_of: datetime,
    reports: Sequence[ReportDoc],
) -> str:
    summary = summarize(config, load_events(config.layout), as_of=as_of)
    price_lines = sorted({doc.price_line for doc in reports if doc.price_line})
    cost_lines = sorted({(doc.repo, doc.cost_line) for doc in reports if doc.cost_line})
    rows: list[Sequence[str]] = [
        ("D10 口径", D10_WORDING),
        (
            "本次分析成本（各报告「成本说明」行）",
            _raw(
                "<br>".join(
                    f"{html.escape(repo)}：{html.escape(line)}" for repo, line in cost_lines
                )
                or "—"
            ),
        ),
        ("全局台账 · 本周 tokens", f"{summary.week_tokens:,}"),
        ("全局台账 · 本月 tokens", f"{summary.month_tokens:,}"),
        ("全局台账 · 本周费用", f"¥{summary.week_cost:.4f}" if summary.cost_complete else "—"),
        ("全局台账 · 本月费用", f"¥{summary.month_cost:.4f}" if summary.cost_complete else "—"),
        ("本周降级 / 预算拦截", f"{summary.week_downgrades} / {summary.week_blocked}"),
        (
            "预算剩余（周 / 月）",
            f"{summary.budget_week_remaining:,} / {summary.budget_month_remaining:,} tok",
        ),
        ("单价来源", PRICE_SOURCE_NOTE),
        ("单价表模型（来自 config）", ", ".join(sorted(config.llm.price_table)) or "—"),
        (
            "单价核对日期（摘自报告「单价」行）",
            _raw(
                "<br>".join(html.escape(line) for line in price_lines)
                or "未获得 + 原因：报告未含单价行；本阶段不做价格复核"
            ),
        ),
        (
            "价格复核",
            "本阶段不做价格复核（定价页正文未获得，E14 / D24 纪律）；"
            "跨月或供应商调价且正文可获得时再核并同步 config.yaml",
        ),
    ]
    return _page(
        "成本",
        '<p class="note">本次分析成本 vs 全局台账两者口径不同（D10）；'
        "站点只读真源，不改写 <code>costs.jsonl</code>。</p>\n" + _table(("项", "值"), rows),
    )


# --------------------------------------------------------------------------- 构建 / 写盘 / 比对


def build_site(config: Config, *, as_of: datetime) -> SitePlan:
    """纯构建：只读真源 → 内存中的静态文件集合。不写盘、不发请求。"""
    layout = config.layout
    reports = load_reports(layout)
    featcards = load_featcards(layout)
    entries = load_library(layout.library_patterns)
    runs = read_jsonl(layout.abstract_runs_jsonl)
    note = empty_patterns_note(config, runs) if not entries else ""
    as_of_text = fmt_iso(as_of)

    run_page, run_rows = _render_runs(runs, note)
    reports_page, report_pages = _render_reports(reports)
    files: dict[str, str] = {
        "index.md": _render_index_md(
            as_of=as_of_text,
            reports=reports,
            featcards=featcards,
            pattern_count=len(entries),
            empty_note=note,
            run_rows=run_rows,
        ),
        "index.html": _render_index_html(
            as_of=as_of_text,
            report_count=len(reports),
            featcard_count=len(featcards),
            pattern_count=len(entries),
            run_count=len(runs),
            empty_note=note,
        ),
        "reports.html": reports_page,
        "featcards.html": _render_featcards(featcards),
        "patterns.html": _render_patterns(entries, note),
        "costs.html": _render_costs(config, as_of=as_of, reports=reports),
        "runs.html": run_page,
        **report_pages,
    }
    return SitePlan(
        files={key: files[key] for key in sorted(files)},
        as_of=as_of_text,
        report_count=len(reports),
        featcard_count=len(featcards),
        pattern_count=len(entries),
        run_count=len(runs),
        empty_note=note,
    )


def site_check(out_dir: Path, files: Mapping[str, str]) -> tuple[str, ...]:
    """只比对不写盘；返回差异清单（空 = 一致）。"""
    diffs: list[str] = []
    for rel, content in sorted(files.items()):
        path = out_dir / rel
        if not path.exists():
            diffs.append(f"缺少 {rel}")
        elif path.read_text(encoding="utf-8") != content:
            diffs.append(f"内容不一致 {rel}")
    expected = set(files)
    if out_dir.exists():
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(out_dir).as_posix()
                if rel not in expected:
                    diffs.append(f"多余 {rel}")
    return tuple(diffs)


def write_site(out_dir: Path, files: Mapping[str, str]) -> tuple[str, ...]:
    """产物只写 out_dir；返回逐文件状态（新增 / 更新 / 未变），不静默覆盖。"""
    statuses: list[str] = []
    for rel, content in sorted(files.items()):
        path = out_dir / rel
        if path.exists():
            state = "未变" if path.read_text(encoding="utf-8") == content else "更新"
        else:
            state = "新增"
        atomic_write_text(path, content)
        statuses.append(f"{state} {rel}")
    return tuple(statuses)
