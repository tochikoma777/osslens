"""特征卡 L0 + 证据层（确定性提取，零 LLM）。

红线 #5：`parallel.hits` / `cache.hits` / `hardware.*` 的每个 `true` **必须**带
`evidence`（file + line + snippet）。本模块只从真实源码行里取证据，取不到就置 `false`——
不存在"应该支持所以标 true"这条路。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .collect import RepoSnapshot, SourceBundle
from .config import Config
from .util import as_int, as_str, days_between, fmt_iso, parse_iso, r4, sort_count_then_path

SCHEMA_VERSION = "1.0"
TOP_MODULES_KEPT = 20
EVIDENCE_LIMIT = 3
SNIPPET_LIMIT = 120
GRAPH_NODE_LIMIT = 40
GRAPH_EXCLUDED_DIRS = frozenset(
    {"tests", "test", "examples", "example", "docs", "third_party", "third-party", "figures"}
)

ENTRYPOINT_NAMES = frozenset(
    {
        "__main__.py",
        "app.py",
        "cli.py",
        "index.js",
        "index.ts",
        "main.cc",
        "main.cpp",
        "main.cu",
        "main.go",
        "main.py",
        "main.rs",
    }
)
GOVERNANCE_DOCS = frozenset(
    {"CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "GOVERNANCE.md", "GOVERNING.md"}
)
MANIFEST_NAMES = frozenset({"Cargo.toml", "go.mod", "package.json", "pyproject.toml"})
PARALLEL_AXES = ("CP", "DP", "EP", "PP", "SP", "TP")
CACHE_AXES = ("kv_offload", "paged", "prefix_reuse", "radix")
PY_SUFFIXES = frozenset({".py"})

PARALLEL_PATTERNS: dict[str, str] = {
    "TP": r"\btensor[\s_-]?parallel\w*",
    "PP": r"\bpipeline[\s_-]?parallel\w*",
    "DP": r"\bdata[\s_-]?parallel\w*",
    "EP": r"\bexpert[\s_-]?parallel\w*",
    "CP": r"\bcontext[\s_-]?parallel\w*",
    "SP": r"\bsequence[\s_-]?parallel\w*",
}
CACHE_PATTERNS: dict[str, str] = {
    "paged": r"\bpaged?[\s_-]?(?:attention|kv|memory|cache)",
    "radix": r"\bradix\b",
    "prefix_reuse": r"\bprefix[\s_-]?(?:cach|reuse)",
    "kv_offload": r"\bkv[\s_-]?(?:cache[\s_-]?)?offload\w*",
}
VENDOR_PATTERNS: dict[str, str] = {
    "amd": r"\b(?:amd|rocm|hip)\b",
    "ascend": r"\b(?:ascend|cann)\b",
    "nvidia": r"\b(?:nvidia|cuda)\b",
}
ARCH_PATTERNS: dict[str, str] = {
    "ampere": r"\b(?:ampere|sm[_-]?80)\b",
    "blackwell": r"\b(?:blackwell|sm[_-]?100)\b",
    "cdna": r"\bcdna\d?\b",
    "hopper": r"\b(?:hopper|sm[_-]?90)\b",
}
KERNEL_LANG_PATTERNS: dict[str, str] = {
    "cuda": r"\.cu\b|\bcuda\b",
    "hip": r"\bhip\b",
    "tilelang": r"\btilelang\b",
    "triton": r"\btriton\b",
}

IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")
INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"')


def build_featcard(
    snapshot: RepoSnapshot,
    *,
    as_of: datetime,
    channel: str,
    config: Config,
    sources: SourceBundle | None = None,
) -> dict[str, Any]:
    data = snapshot.data
    repo = _dict(data.get("repo"))
    commits = _rows(data.get("commits"))
    contributors = _rows(data.get("contributors"))
    releases = _rows(data.get("releases"))
    languages = _int_map(data.get("languages"))
    entries = _rows(_dict(data.get("tree")).get("entries"))

    created_at = as_str(repo.get("created_at"))
    age_days = days_between(as_of, parse_iso(created_at)) if created_at else None

    structure = _structure(entries)
    has_governance_docs = bool(structure.pop("_has_governance_docs", False))
    last_commit = as_str(commits[0].get("date")) if commits else as_str(repo.get("pushed_at"))
    days_since_commit = days_between(as_of, parse_iso(last_commit)) if last_commit else None

    total_contributions = sum(as_int(row.get("contributions")) for row in contributors)
    top10_contributions = sum(as_int(row.get("contributions")) for row in contributors[:10])
    top10_share = r4(top10_contributions / total_contributions) if total_contributions else None
    bus_factor = None
    if total_contributions and contributors:
        bus_factor = r4(as_int(contributors[0].get("contributions")) / total_contributions)

    files = _source_texts(sources)
    parallel_hits, parallel_evidence = _scan(files, PARALLEL_PATTERNS)
    cache_hits, cache_evidence = _scan(files, CACHE_PATTERNS)
    vendors, _ = _scan(files, VENDOR_PATTERNS)
    arch_gates, _ = _scan(files, ARCH_PATTERNS)
    kernel_langs, _ = _scan(files, KERNEL_LANG_PATTERNS)
    graph = _build_graph(files)

    return {
        "schema_version": SCHEMA_VERSION,
        "identity": {
            "repo": snapshot.slug,
            "commit": as_str(commits[0].get("sha")) if commits else "",
            "analyzed_at": fmt_iso(as_of),
            "channel": channel,
            "created_at": created_at,
            "age_days": age_days,
        },
        "scale": {
            "stars": as_int(repo.get("stars")),
            "forks": as_int(repo.get("forks")),
            "open_issues": as_int(repo.get("open_issues")),
            "used_by": None,
            "contributors": len(contributors),
            "top10_share": top10_share,
            "commits_90d": _count_commits_since(commits, as_of, days=90),
            "commits_365d": len(commits),
            "last_commit": last_commit,
            "release_count_365d": _count_releases_since(releases, as_of, days=365),
        },
        "lang": {"shares": _language_shares(languages)},
        "structure": structure,
        "deps": {
            "direct": None,
            "transitive": None,
            "external_top": [],
            "internal_edge_count": len(graph["edges"]),
            "graph": graph,
        },
        "parallel": {
            "hits": {axis: axis in parallel_hits for axis in PARALLEL_AXES},
            "evidence": {
                axis: parallel_evidence[axis] for axis in PARALLEL_AXES if axis in parallel_evidence
            },
        },
        "cache": {
            "hits": {axis: axis in cache_hits for axis in CACHE_AXES},
            "evidence": {
                axis: cache_evidence[axis] for axis in CACHE_AXES if axis in cache_evidence
            },
        },
        "hardware": {
            "vendors": sorted(vendors),
            "arch_gates": sorted(arch_gates),
            "kernel_langs": sorted(kernel_langs),
            "lock_in_score": None,
        },
        "governance": {
            "org_type": _org_type(repo),
            "license": as_str(repo.get("license")),
            "has_governance_docs": has_governance_docs,
            "cncf_or_foundation": None,
        },
        "signals": {
            "maintenance_state": _maintenance_state(
                archived=_flag(repo.get("archived")),
                days_since_commit=days_since_commit,
                active_days=config.featcard.maintenance.active_days,
                slowed_days=config.featcard.maintenance.slowed_days,
            ),
            "days_since_commit": days_since_commit,
            "bus_factor_top1_share": bus_factor,
            "issue_close_ratio_90d": None,
        },
        "sources": {
            "commit": sources.commit if sources else "",
            "tarball_sha256": sources.tarball_sha256 if sources else "",
            "files": (
                [{"path": item.path, "sha256": item.sha256} for item in sources.files]
                if sources
                else []
            ),
        },
        "limitations": _limitations(snapshot, sources),
    }


def depgraph_mermaid(graph: dict[str, Any]) -> str:
    """设计方案 §6.5：`graph TD`、节点清洗、边排序、空态不省略。"""
    pairs: list[tuple[str, str]] = []
    raw_edges = graph.get("edges")
    if isinstance(raw_edges, list):
        for item in raw_edges:
            if isinstance(item, list) and len(item) == 2:
                pairs.append((as_str(item[0]), as_str(item[1])))
    if not pairs:
        return "graph TD\n  A[无可提取的内部模块依赖边]"

    pairs.sort()
    ids: dict[str, str] = {}
    lines = ["graph TD"]
    for source, target in pairs:
        for node in (source, target):
            if node not in ids:
                ids[node] = _mermaid_id(node, len(ids))
        lines.append(f"  {ids[source]} --> {ids[target]}")
    return "\n".join(lines)


def _mermaid_id(node: str, index: int) -> str:
    cleaned = re.sub(r"\W", "_", node)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n{index}_{cleaned}"
    return cleaned


def _scan(
    files: Sequence[tuple[str, str]], patterns: dict[str, str]
) -> tuple[set[str], dict[str, list[dict[str, Any]]]]:
    """逐行扫描；每个轴最多留 EVIDENCE_LIMIT 条证据，按 (file, line) 确定性排序。"""
    hits: set[str] = set()
    evidence: dict[str, list[dict[str, Any]]] = {}
    compiled = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in patterns.items()}
    for name in sorted(compiled):
        found: list[dict[str, Any]] = []
        for path, text in files:
            for line_no, line in enumerate(text.splitlines(), start=1):
                if not compiled[name].search(line):
                    continue
                found.append(
                    {"file": path, "line": line_no, "snippet": line.strip()[:SNIPPET_LIMIT]}
                )
        if found:
            hits.add(name)
            evidence[name] = sorted(
                found,
                key=lambda item: (
                    Path(as_str(item["file"])).name.lower().startswith("readme"),
                    as_str(item["file"]),
                    as_int(item["line"]),
                ),
            )[:EVIDENCE_LIMIT]
    return hits, evidence


def _source_texts(sources: SourceBundle | None) -> list[tuple[str, str]]:
    """README 排最后：代码里的证据比文档里的声明更硬。"""
    if sources is None:
        return []
    items = sources.texts()
    return sorted(
        ((item.path, text) for item, text in items),
        key=lambda pair: (Path(pair[0]).name.lower().startswith("readme"), pair[0]),
    )


def _build_graph(files: Sequence[tuple[str, str]]) -> dict[str, Any]:
    modules: dict[str, str] = {}
    for path, _text in files:
        if path.split("/", 1)[0] in GRAPH_EXCLUDED_DIRS:
            continue
        key = _module_key(path)
        if key:
            modules[key] = path
    by_basename = {Path(path).name: key for key, path in modules.items()}

    edges: set[tuple[str, str]] = set()
    for path, text in files:
        if path.split("/", 1)[0] in GRAPH_EXCLUDED_DIRS:
            continue
        source_key = _module_key(path)
        if not source_key:
            continue
        if Path(path).suffix.lower() in PY_SUFFIXES:
            for line in text.splitlines():
                match = IMPORT_RE.match(line)
                if match is None:
                    continue
                target = _resolve_python(match.group(1) or match.group(2), path, modules)
                if target and target != source_key:
                    edges.add((source_key, target))
        for match in INCLUDE_RE.finditer(text):
            target = by_basename.get(Path(match.group(1)).name)
            if target and target != source_key:
                edges.add((source_key, target))

    degree: dict[str, int] = {}
    for source, target in edges:
        degree[source] = degree.get(source, 0) + 1
        degree[target] = degree.get(target, 0) + 1
    keep = {
        node
        for node, _count in sorted(degree.items(), key=lambda item: (-item[1], item[0]))[
            :GRAPH_NODE_LIMIT
        ]
    }
    kept_edges = sorted(
        (source, target) for source, target in edges if source in keep and target in keep
    )
    nodes = sorted({node for edge in kept_edges for node in edge})
    return {
        "nodes": nodes,
        "edges": [[source, target] for source, target in kept_edges],
        "truncated": len(kept_edges) < len(edges) or len(keep) < len(degree),
    }


def _module_key(path: str) -> str:
    suffix = Path(path).suffix
    key = path[: -len(suffix)] if suffix else path
    if key.endswith("/__init__"):
        key = key[: -len("/__init__")]
    return key


def _resolve_python(name: str, path: str, modules: dict[str, str]) -> str | None:
    if not name:
        return None
    if name.startswith("."):
        level = len(name) - len(name.lstrip("."))
        remainder = name.lstrip(".")
        package_parts = list(Path(path).parent.parts)
        drop = level - 1
        if drop > 0:
            package_parts = package_parts[:-drop] if drop <= len(package_parts) else []
        parts = [*package_parts, *[part for part in remainder.split(".") if part]]
    else:
        parts = [part for part in name.split(".") if part]
    for end in range(len(parts), 0, -1):
        candidate = "/".join(parts[:end])
        if candidate in modules:
            return candidate
    return None


def _structure(entries: list[dict[str, Any]]) -> dict[str, Any]:
    blobs = [row for row in entries if as_str(row.get("type")) == "blob"]
    files: dict[str, int] = {}
    sizes: dict[str, int] = {}
    entrypoints: list[str] = []
    paths: list[str] = []
    for row in blobs:
        path = as_str(row.get("path"))
        paths.append(path)
        size = as_int(row.get("size"))
        module = path.split("/", 1)[0] if "/" in path else "."
        files[module] = files.get(module, 0) + 1
        sizes[module] = sizes.get(module, 0) + size
        if path.rsplit("/", 1)[-1] in ENTRYPOINT_NAMES:
            entrypoints.append(path)

    top_modules = [
        {"path": path, "files": files[path], "bytes": size}
        for path, size in sort_count_then_path(sizes.items())[:TOP_MODULES_KEPT]
    ]
    manifests = {
        path.split("/", 1)[0]
        for path in paths
        if "/" in path and path.rsplit("/", 1)[-1] in MANIFEST_NAMES
    }
    return {
        "entrypoints": sorted(entrypoints),
        "top_modules": top_modules,
        "max_depth": max((path.count("/") + 1 for path in paths), default=0),
        "monorepo": len(manifests) >= 2,
        "loc_total": None,
        "files": len(blobs),
        "bytes": sum(as_int(row.get("size")) for row in blobs),
        "_has_governance_docs": any("/" not in path and path in GOVERNANCE_DOCS for path in paths),
    }


def _language_shares(languages: dict[str, int]) -> dict[str, float]:
    total = sum(languages.values())
    if total <= 0:
        return {}
    return {name: r4(bytes_count / total) for name, bytes_count in sorted(languages.items())}


def _count_commits_since(commits: list[dict[str, Any]], as_of: datetime, *, days: int) -> int:
    threshold = as_of - timedelta(days=days)
    return sum(
        1
        for row in commits
        if as_str(row.get("date")) and parse_iso(as_str(row.get("date"))) >= threshold
    )


def _count_releases_since(releases: list[dict[str, Any]], as_of: datetime, *, days: int) -> int:
    threshold = as_of - timedelta(days=days)
    count = 0
    for row in releases:
        if _flag(row.get("draft")):
            continue
        published = as_str(row.get("published_at"))
        if published and parse_iso(published) >= threshold:
            count += 1
    return count


def _maintenance_state(
    *, archived: bool, days_since_commit: int | None, active_days: int, slowed_days: int
) -> str:
    if archived:
        return "archived"
    if days_since_commit is None:
        return "unknown"
    if days_since_commit <= active_days:
        return "active"
    if days_since_commit <= slowed_days:
        return "slowed"
    return "maintenance"


def _org_type(repo: dict[str, Any]) -> str | None:
    """Organization 无法从元数据区分 company / foundation / community，故置 null。"""
    if as_str(repo.get("owner_type")) == "User":
        return "personal"
    return None


def _limitations(snapshot: RepoSnapshot, sources: SourceBundle | None) -> list[str]:
    notes: list[str] = []
    if sources is None or not sources.files:
        notes.append(
            "未取得源码切片：parallel/cache/hardware 全部 false、deps.graph 为空（红线 #5）"
        )
    else:
        notes.append(f"证据来自 {len(sources.files)} 个源码切片的逐行扫描，未覆盖文件不计入")
    notes.extend(
        [
            "issue_close_ratio_90d 需 search API，L0/L1 未调用",
            "cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null",
        ]
    )
    for note in snapshot.notes:
        if note.status != "unavailable":
            notes.append(f"{note.source}: {note.status} — {note.reason}")
    return notes


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): as_int(item) for key, item in value.items()}


def _flag(value: Any) -> bool:
    return value if isinstance(value, bool) else False


__all__ = ["SCHEMA_VERSION", "build_featcard", "depgraph_mermaid"]
