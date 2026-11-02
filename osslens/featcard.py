"""特征卡 L0（确定性提取，零 LLM）。

硬约束（红线 #5）：`parallel.hits` / `cache.hits` / `hardware.*` 的每个 `true` 必须带
evidence（file + line + snippet）。L0 只跑元数据层，拿不到源码行号，因此**全部置 false**，
并把"为什么没有"写进 `limitations`——这不是缺陷，是诚实。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .collect import RepoSnapshot
from .util import as_int, as_str, days_between, fmt_iso, parse_iso, r4, sort_count_then_path

SCHEMA_VERSION = "1.0"
TOP_MODULES_KEPT = 20

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


def build_featcard(snapshot: RepoSnapshot, *, as_of: datetime, channel: str) -> dict[str, Any]:
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
            "internal_edge_count": None,
        },
        "parallel": {"hits": _false_map(PARALLEL_AXES), "evidence": {}},
        "cache": {"hits": _false_map(CACHE_AXES), "evidence": {}},
        "hardware": {
            "vendors": [],
            "arch_gates": [],
            "kernel_langs": [],
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
            ),
            "days_since_commit": days_since_commit,
            "bus_factor_top1_share": bus_factor,
            "issue_close_ratio_90d": None,
        },
        "limitations": _limitations(snapshot),
    }


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


def _maintenance_state(*, archived: bool, days_since_commit: int | None) -> str:
    if archived:
        return "archived"
    if days_since_commit is None:
        return "unknown"
    if days_since_commit <= 90:
        return "active"
    if days_since_commit <= 365:
        return "slowed"
    return "maintenance"


def _org_type(repo: dict[str, Any]) -> str | None:
    """Organization 无法从元数据区分 company / foundation / community，故置 null。"""
    if as_str(repo.get("owner_type")) == "User":
        return "personal"
    return None


def _limitations(snapshot: RepoSnapshot) -> list[str]:
    notes = [
        "L0 只跑元数据层：未读取源码内容，parallel/cache/hardware 全部 false，"
        "deps.* 与 loc_total 为 null（红线 #5：无证据不写入）",
        "issue_close_ratio_90d 需 search API，L0 未调用",
        "cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，L0 置 null",
    ]
    for note in snapshot.notes:
        if note.status != "unavailable":
            notes.append(f"{note.source}: {note.status} — {note.reason}")
    return notes


def _false_map(keys: tuple[str, ...]) -> dict[str, bool]:
    return dict.fromkeys(keys, False)


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
