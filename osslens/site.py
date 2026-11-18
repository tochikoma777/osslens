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
    paradigm_tags: tuple[str, ...] = ()
    # 报告头部「成本异常（仅标注，不阻断）」区块的条目（无异常时为空）。
    anomalies: tuple[str, ...] = ()


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


# 报告洞见段里由 render.py 写出的「- 架构范式标签：」行（受控词表，顿号分隔）。
_TAG_LINE = re.compile(r"^-\s*架构范式标签：(.+)$")

# render.py 写出的头部异常区块标记（只用于站点呈现，不改写报告正文）。
_ANOMALY_MARKER = "> ⚠ **成本异常（仅标注，不阻断）**"


def _report_anomalies(text: str) -> tuple[str, ...]:
    """解析报告头部「成本异常」区块的 `> - ` 条目；无区块返回空。"""
    items: list[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_ANOMALY_MARKER):
            in_block = True
            continue
        if not in_block:
            continue
        if stripped.startswith("> - "):
            items.append(stripped[len("> - ") :].strip())
            continue
        if stripped.startswith(">"):
            continue
        break
    return tuple(items)


def _report_paradigm_tags(text: str) -> tuple[str, ...]:
    """从报告洞见段解析架构范式标签；只认受控词表内的值（确定性，绝不猜）。"""
    from .llm import PARADIGM_TAGS  # 局部导入：与 prompt/schema 单一真源

    found: set[str] = set()
    for line in text.splitlines():
        match = _TAG_LINE.match(line.strip())
        if not match:
            continue
        for tag in re.split(r"[、,，/\s]+", match.group(1)):
            cleaned = tag.strip()
            if cleaned in PARADIGM_TAGS:
                found.add(cleaned)
    return tuple(sorted(found))


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
                paradigm_tags=_report_paradigm_tags(text),
                anomalies=_report_anomalies(text),
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
    ":root{--bg:#f4f7fb;--surface:#fff;--ink:#14213d;--muted:#64748b;--line:#e2e8f0;"
    "--brand:#2563eb;--brand2:#06b6d4;--radius:16px;--shadow:0 10px 30px rgba(15,23,42,.07)}\n"
    "*{box-sizing:border-box}\n"
    "body{margin:0;font-family:system-ui,-apple-system,'Segoe UI','PingFang SC',"
    "'Microsoft YaHei',sans-serif;"
    "background:var(--bg);color:var(--ink);line-height:1.65}\n"
    ".site-header{background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 55%,#0e7490 100%);"
    "color:#fff;padding:30px 24px 24px}\n"
    ".wrap{max-width:1120px;margin:0 auto}\n"
    ".brand{display:flex;align-items:center;gap:12px;margin-bottom:18px}\n"
    ".brand-mark{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;"
    "font-weight:800;background:linear-gradient(135deg,#38bdf8,#2563eb);"
    "box-shadow:0 6px 18px rgba(0,0,0,.25)}\n"
    ".brand small{display:block;color:#bfdbfe;letter-spacing:.16em;"
    "font-size:.72em;text-transform:uppercase}\n"
    "header h1{font-size:1.9rem;margin:0 0 16px;letter-spacing:.01em}\n"
    "header nav{display:flex;flex-wrap:wrap;gap:8px}\n"
    "header nav a{color:#e0f2fe;text-decoration:none;padding:6px 12px;border-radius:999px;"
    "background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);font-size:.88em}\n"
    "header nav a:hover,header nav a.active{background:#fff;"
    "color:#1e3a8a;border-color:transparent}\n"
    "main{max-width:1120px;margin:26px auto 0;padding:0 24px}\n"
    "main>section,main>.panel{background:var(--surface);border:1px solid var(--line);"
    "border-radius:var(--radius);padding:22px 24px;"
    "box-shadow:var(--shadow);margin-bottom:20px}\n"
    "h1,h2,h3{line-height:1.25;color:#0f172a}\n"
    ".site-header h1,.site-header h2{color:#fff}\n"
    "h2{font-size:1.3rem;margin:0 0 12px}"
    "h3{font-size:1.06rem;margin:22px 0 8px}\n"
    "p{margin:8px 0}a{color:#1d4ed8}\n"
    "code{background:#eef2ff;color:#3730a3;padding:2px 6px;border-radius:6px;font-size:.9em}\n"
    "pre{background:#0f172a;color:#e2e8f0;padding:16px;border-radius:12px;overflow:auto}\n"
    "pre code{background:none;color:inherit;padding:0}\n"
    ".hero{background:linear-gradient(135deg,#eff6ff,#f0fdfa);border-color:#bfdbfe}\n"
    ".hero h2{font-size:1.55rem;margin:4px 0 8px}\n"
    ".kicker{color:var(--brand);font-weight:700;letter-spacing:.14em;font-size:.72em;margin:0}\n"
    ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));"
    "gap:14px;margin:18px 0}\n"
    ".stat{display:block;text-decoration:none;color:inherit;background:#fff;"
    "border:1px solid var(--line);"
    "border-radius:14px;padding:18px;transition:transform .18s,border-color .18s;"
    "box-shadow:0 4px 14px rgba(15,23,42,.04)}\n"
    ".stat:hover{transform:translateY(-2px);border-color:#93c5fd;"
    "box-shadow:0 12px 24px rgba(37,99,235,.12)}\n"
    ".stat-label{display:block;color:var(--muted);font-size:.82em}\n"
    ".stat strong{display:block;font-size:2rem;line-height:1.2;margin:6px 0;"
    "background:linear-gradient(90deg,var(--brand),var(--brand2));-webkit-background-clip:text;"
    "background-clip:text;color:transparent}\n"
    ".stat-desc{color:var(--muted);font-size:.78em}\n"
    ".table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}\n"
    "table{border-collapse:collapse;width:100%;margin:0;background:#fff;font-size:.92em}\n"
    "th,td{padding:10px 14px;text-align:left;vertical-align:top;"
    "border-bottom:1px solid var(--line)}\n"
    "th{background:#f8fafc;color:#334155;font-weight:600;white-space:nowrap;position:sticky;top:0}\n"
    "tbody tr:hover{background:#f8fbff}tbody tr:last-child td{border-bottom:0}\n"
    ".empty,.note{background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;margin:14px 0;"
    "border-radius:0 10px 10px 0;color:#78350f}\n"
    ".alert{background:#ffeef0;border-left:4px solid #d1242f;padding:12px 16px;margin:14px 0;"
    "border-radius:0 10px 10px 0;color:#7f1d1d}\n"
    ".badge-alert{display:inline-block;background:#d1242f;color:#fff;border-radius:999px;"
    "padding:2px 10px;font-size:.8em;font-weight:700}\n"
    ".pill{display:inline-block;background:#eff6ff;color:#1e40af;border:1px solid #dbeafe;"
    "border-radius:999px;padding:2px 10px;font-size:.78em;margin:2px}\n"
    "footer{max-width:1120px;margin:0 auto;padding:22px 24px 36px;color:var(--muted);"
    "font-size:.82em;text-align:center}\n"
    "@media(max-width:700px){header h1{font-size:1.45rem}main{padding:0 14px}"
    "main>section,main>.panel{padding:16px}.grid{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}}\n"
)

_NAV_ITEMS = (
    ("首页", "index.html"),
    ("报告", "reports.html"),
    ("时间线", "timeline.html"),
    ("特征卡", "featcards.html"),
    ("规律库", "patterns.html"),
    ("成本", "costs.html"),
    ("抽象 run", "runs.html"),
    ("检索", "search.html"),
    ("范式标签", "tags.html"),
    ("并排对比", "compare.html"),
)


def _page(title: str, body: str) -> str:
    active = (
        "首页"
        if title.startswith("osslens")
        else max((label for label, _ in _NAV_ITEMS if label in title), key=len, default="")
    )
    links: list[str] = []
    for label, url in _NAV_ITEMS:
        cls = ' class="active"' if label == active else ""
        links.append(f'<a{cls} href="{url}">{html.escape(label)}</a>')
    nav = " · ".join(links)
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{html.escape(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        '<header class="site-header"><div class="wrap">'
        '<div class="brand"><span class="brand-mark">O</span>'
        "<div><small>osslens / static insights</small></div></div>"
        f"<h1>{html.escape(title)}</h1><nav>{nav}</nav>"
        "</div></header>\n"
        f'<main class="wrap">\n{body}\n</main>\n'
        "<footer>osslens 静态只读站点 · 无后端 / 无外部 JS 与 CDN / 零 LLM / 零网络</footer>\n"
        "</body></html>\n"
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        f'<div class="table-wrap"><table class="data-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


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
    stats = (
        ("报告", report_count, "reports.html", "五区块顺序固定"),
        ("特征卡", featcard_count, "featcards.html", "file:line 证据"),
        ("规律库", pattern_count, "patterns.html", "真源条目"),
        ("抽象 run", run_count, "runs.html", "九字段记录"),
        ("检索", report_count, "search.html", "本地静态索引"),
        ("并排对比", featcard_count, "compare.html", "固定前三张卡"),
    )
    cards = "".join(
        f'<a class="stat" href="{url}"><span class="stat-label">{html.escape(label)}</span>'
        f'<strong>{count}</strong><span class="stat-desc">{html.escape(desc)}</span></a>'
        for label, count, url, desc in stats
    )
    empty_block = (
        f'<div class="empty"><strong>{html.escape(empty_note)}</strong></div>'
        if pattern_count == 0
        else '<div class="note">规律库已有条目，可在规律库页查看。</div>'
    )
    body = "\n".join(
        [
            '<section class="hero panel">'
            '<p class="kicker">STATIC · READ-ONLY · DETERMINISTIC</p>'
            "<h2>把开源项目的证据，变成可阅读的知识</h2>"
            f"<p>基准时间 (as-of)：<code>{html.escape(as_of)}</code>。"
            "时间只来自 <code>--as-of</code> 或输入真源，不含运行时钟。</p>"
            "</section>",
            f'<div class="grid">{cards}</div>',
            "<section>"
            + empty_block
            + '<div class="note">站点为只读静态产物，可丢弃、可重建；不改写任何真源。'
            + '另见 <a href="tags.html">范式标签</a> 与 <a href="costs.html">成本</a>。'
            + "<code>index.md</code> 是纯文本索引，供下载 / 编辑器阅读；浏览器请直接用本页。</div>"
            + "</section>",
        ]
    )
    return _page("osslens · 静态只读站点", body)


def _intro(kicker: str, title: str, text: str) -> str:
    """统一的页内导言块：标题上方小标签 + 一句话说明。"""
    return (
        f'<section><p class="kicker">{html.escape(kicker)}</p>'
        f"<h2>{html.escape(title)}</h2><p>{html.escape(text)}</p></section>"
    )


def _anomaly_alert(pairs: Sequence[tuple[str, str]]) -> str:
    """红色告警块：与 .empty/.note（黄色提示）及普通 warnings 文本区分。"""
    if not pairs:
        return ""
    items = "".join(f"<li>{html.escape(repo)}：{html.escape(text)}</li>" for repo, text in pairs)
    return (
        '<div class="alert"><span class="badge-alert">⚠ 成本异常（仅标注，不阻断）</span>'
        f"<ul>{items}</ul></div>\n"
    )


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
        _intro(
            "REPORTS / DEEP DIVES",
            "单项目分析报告",
            f"当前 {len(reports)} 份；每份固定五区块，时间只来自 as-of 或真源。",
        )
        + (
            _table(("仓库", "基准时间 (as-of)", "实际档位", "链接"), rows)
            if rows
            else '<p class="empty">暂无报告（空态，不伪造内容）。</p>'
        ),
    )
    pages = {
        f"report-{doc.stem}.html": _page(
            f"报告 · {doc.repo}",
            f'<p class="note">源 MD：<code>../reports/{html.escape(doc.stem)}.md</code>；'
            "下方五区块顺序固定不变。</p>\n"
            + _anomaly_alert([(doc.repo, item) for item in doc.anomalies])
            + md_to_html(doc.text),
        )
        for doc in reports
    }
    return listing, pages


def _render_timeline(reports: Sequence[ReportDoc]) -> str:
    """按 as-of 的年月分组报告，提供可读的时间线视图（纯静态、无脚本）。"""
    intro = _intro(
        "TIMELINE / ARCHIVE",
        "时间线归档",
        "报告按基准时间 (as-of) 的年月分组；点击条目阅读完整报告。",
    )
    if not reports:
        return _page("时间线", intro + '<p class="empty">暂无报告（空态，不伪造内容）。</p>')
    by_month: dict[str, list[ReportDoc]] = {}
    for doc in reports:
        by_month.setdefault((doc.as_of or "未知")[:7], []).append(doc)
    sections: list[str] = []
    for month in sorted(by_month, reverse=True):
        docs = sorted(by_month[month], key=lambda item: (item.as_of, item.repo), reverse=True)
        items = "".join(
            f'<li><a href="report-{html.escape(doc.stem)}.html">{html.escape(doc.repo)}</a>'
            f" · {html.escape(doc.as_of)} · {html.escape(doc.depth)}</li>"
            for doc in docs
        )
        sections.append(
            f'<h3>{html.escape(month)} <span class="pill">{len(docs)} 份</span></h3>'
            f"<ul>{items}</ul>"
        )
    return _page("时间线", intro + "".join(sections))


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
        _intro(
            "EVIDENCE / FEATURE CARDS",
            "确定性提取的特征卡",
            f"当前 {len(cards)} 张；代码证据以 file:line 留痕，缺失则如实标注。",
        )
        + (body if rows else '<p class="empty">暂无特征卡（空态，不伪造内容）。</p>'),
    )


def _render_patterns(entries: Sequence[PatternEntry], empty_note: str) -> str:
    if not entries:
        return _page(
            "规律库",
            _intro(
                "PATTERNS / LIVING LIBRARY",
                "规律库",
                "只收录由真实样本与代码证据支撑的条目；宁可空态，不用合成条目充数。",
            )
            + f'<div class="empty"><strong>{html.escape(empty_note)}</strong></div>'
            + "<p>真源 <code>patterns/library.yaml</code> 为 <code>[]</code>；"
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
        _intro(
            "PATTERNS / LIVING LIBRARY",
            "规律库",
            f"当前 {len(entries)} 条；每条都必须能下钻到真实样本的代码证据。",
        )
        + _table(("id", "层", "簇", "陈述", "状态", "正例", "反例", "revision"), rows),
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
    anomaly_pairs = sorted({(doc.repo, item) for doc in reports for item in doc.anomalies})
    return _page(
        "成本",
        _intro(
            "COST / GUARDRAILS",
            "成本与预算",
            "闸门按时发生，台账按事件留痕；只标注异常，不阻断产出。",
        )
        + _anomaly_alert(anomaly_pairs)
        + '<p class="note">本次分析成本 vs 全局台账两者口径不同（D10）；'
        "站点只读真源，不改写 <code>costs.jsonl</code>。</p>\n" + _table(("项", "值"), rows),
    )


# --------------------------------------------------------------------------- 构建 / 写盘 / 比对


# --------------------------------------------------------------------------- Q2 静态三能力（T3）


def _tag_anchor(tag: str) -> str:
    """标签 → 站内锚点 id（确定性，转义后仅保留安全字符）。"""
    import hashlib

    return "tag-" + hashlib.sha256(tag.encode("utf-8")).hexdigest()[:10]


def _render_search(
    reports: Sequence[ReportDoc], featcards: Sequence[FeatcardDoc]
) -> tuple[str, str]:
    """检索：预生成本地索引（HTML 锚点 + JSON 数据），零脚本、零外部依赖。

    - ``search.html``：按仓库名 / 关键词的**静态**可查索引，站内锚点跳转；
      关键词 = 仓库名片段 + 架构范式标签 + 实际档位（全部来自真源，不猜）。
    - ``search-index.json``：可脱离站点阅读的本地 JSON 索引（MD/JSON，无外部依赖）。
    ★ 无 <script> / 无 JS / 无网络：用浏览器自带的页内查找或锚点即可定位。
    """
    rows: list[dict[str, Any]] = []
    for doc in reports:
        keywords = sorted(
            {part for part in re.split(r"[/_\-.]+", doc.repo) if part and len(part) > 1}
            | set(doc.paradigm_tags)
            | ({doc.depth} if doc.depth and doc.depth != "—" else set())
        )
        rows.append(
            {
                "repo": doc.repo,
                "as_of": doc.as_of,
                "depth": doc.depth,
                "paradigm_tags": list(doc.paradigm_tags),
                "keywords": keywords,
                "url": f"report-{doc.stem}.html",
            }
        )
    index_json = json.dumps({"entries": rows}, ensure_ascii=False, sort_keys=True) + "\n"

    body_rows = [
        (
            _raw(f'<a href="{html.escape(row["url"])}">{html.escape(row["repo"])}</a>'),
            row["as_of"] or "—",
            row["depth"],
            "、".join(row["paradigm_tags"]) or "—",
            "、".join(row["keywords"]) or "—",
        )
        for row in rows
    ]
    # 关键词 → 仓库的静态倒排（锚点分组），确定性排序
    inverted: dict[str, list[str]] = {}
    for row in rows:
        for keyword in row["keywords"]:
            inverted.setdefault(keyword, []).append(row["repo"])
    keyword_lines = [
        f"<li><strong>{html.escape(kw)}</strong>："
        + "、".join(html.escape(repo) for repo in sorted(set(repos)))
        + "</li>"
        for kw, repos in sorted(inverted.items())
    ]
    body = "\n".join(
        [
            '<p class="note">纯静态本地索引（零脚本 / 零网络 / 无外部依赖）。'
            "可用浏览器页内查找按仓库名或关键词定位；下方并附关键词倒排与 "
            '<a href="search-index.json">JSON 索引</a>。</p>',
            "<h2>按仓库名</h2>",
            _table(("仓库", "as-of", "档位", "范式标签", "关键词"), body_rows)
            if body_rows
            else '<p class="empty">暂无报告（空态，不伪造内容）。</p>',
            "<h2>按关键词</h2>",
            "<ul>" + "".join(keyword_lines) + "</ul>" if keyword_lines else "<p>—</p>",
        ]
    )
    return _page("检索 · 本地静态索引", body), index_json


def _render_tags(reports: Sequence[ReportDoc]) -> str:
    """标签过滤：以 paradigm_tags 为数据源的静态列表页（站内锚点，零脚本）。

    ★ 真源纯净：当前若无 fast/strong 报告带范式标签，显示诚实空态，绝不伪造条目（红线 8）。
    """
    from .llm import PARADIGM_TAGS

    by_tag: dict[str, list[ReportDoc]] = {}
    for doc in reports:
        for tag in doc.paradigm_tags:
            by_tag.setdefault(tag, []).append(doc)

    # 词表全量（含 0 条的标签）作为可枚举的过滤维度，计数来自真源
    tag_rows = [
        (
            _raw(f'<a href="#{_tag_anchor(tag)}">{html.escape(tag)}</a>'),
            str(len(by_tag.get(tag, []))),
        )
        for tag in sorted(PARADIGM_TAGS)
    ]
    sections: list[str] = []
    for tag in sorted(PARADIGM_TAGS):
        docs = sorted(by_tag.get(tag, []), key=lambda item: (item.repo, item.as_of))
        links = "".join(
            f'<li><a href="report-{html.escape(doc.stem)}.html">'
            f"{html.escape(doc.repo)}</a>（{html.escape(doc.as_of or '—')}）</li>"
            for doc in docs
        )
        sections.append(
            f'<h2 id="{_tag_anchor(tag)}">{html.escape(tag)}</h2>'
            + (f"<ul>{links}</ul>" if links else '<p class="empty">该标签下暂无报告。</p>')
        )

    total = sum(len(v) for v in by_tag.values())
    head = (
        f'<p class="note">数据源 = 报告洞见段的 <code>paradigm_tags</code>（受控词表，'
        f"共 {len(PARADIGM_TAGS)} 个标签 / {total} 次标注）。纯静态锚点过滤，零脚本。</p>"
    )
    empty = (
        '<div class="empty">当前无 fast/strong 报告带架构范式标签（现有报告多为 off 档，'
        "洞见位为 —）。标签体系与过滤页已预生成，待带标签的报告接入后自动填充；不伪造条目。</div>"
        if total == 0
        else ""
    )
    body = "\n".join(
        [
            head,
            empty,
            "<h2>标签总览</h2>",
            _table(("标签", "报告数"), tag_rows),
            *sections,
        ]
    )
    return _page("范式标签 · 静态过滤", body)


def _render_compare(featcards: Sequence[FeatcardDoc]) -> str:
    """并排对比：选 2–3 个项目特征卡的静态并排表（纯 HTML，零脚本 / 零网络）。

    取按 repo 稳定排序后的前 3 张特征卡（确定性，不随机、不读运行时钟）。
    """
    picks = sorted(featcards, key=lambda item: (item.repo, item.commit))[:3]
    if len(picks) < 2:
        return _page(
            "并排对比",
            '<p class="empty">可用特征卡不足 2 张，无法并排对比（空态，不伪造内容）。</p>',
        )
    rows: list[Sequence[str]] = [
        ("仓库", *[card.repo for card in picks]),
        ("commit", *[card.commit[:12] or "—" for card in picks]),
        ("analyzed_at", *[card.analyzed_at or "—" for card in picks]),
        ("通道", *[card.channel or "—" for card in picks]),
        ("stars", *[str(card.stars) for card in picks]),
        (
            "代码证据条数",
            *[str(len(card.evidence)) for card in picks],
        ),
        (
            "代码证据 file:line",
            *[_raw("<br>".join(html.escape(p) for p in card.evidence) or "—") for card in picks],
        ),
    ]
    body = "\n".join(
        [
            _intro(
                "COMPARE / SIDE BY SIDE",
                "并排对比",
                f"按仓库名稳定排序取前 {len(picks)} 张特征卡，逐字段对照；零脚本 / 零网络。",
            ),
            '<p class="note">纯静态并排对比（取按仓库名排序的前 '
            f"{len(picks)} 张特征卡，确定性）；零脚本 / 零网络 / 无外部依赖。</p>",
            _table(("字段", *[f"项目 {i + 1}" for i in range(len(picks))]), rows),
        ]
    )
    return _page("并排对比", body)


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
    search_page, search_index = _render_search(reports, featcards)
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
        "timeline.html": _render_timeline(reports),
        "featcards.html": _render_featcards(featcards),
        "patterns.html": _render_patterns(entries, note),
        "costs.html": _render_costs(config, as_of=as_of, reports=reports),
        "runs.html": run_page,
        "search.html": search_page,
        "search-index.json": search_index,
        "tags.html": _render_tags(reports),
        "compare.html": _render_compare(featcards),
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
