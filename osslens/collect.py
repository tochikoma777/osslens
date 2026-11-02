"""GitHub 快照采集（零 LLM）。

设计约束：
- 所有时间来自 `as_of` 或采集时刻，报告不使用 `datetime.now()`。
- 每个可选来源独立降级：单源失败只记 note，不影响退出码（红线 "单源失败不影响退出码"）。
- 快照落盘 + sha256，作为幂等的**输入**：同一 `as_of` 重跑复用同一快照。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import Layout
from .util import (
    Clock,
    HttpClient,
    HttpError,
    OsslensError,
    UsageError,
    as_bool,
    as_dict,
    as_int,
    as_list,
    as_str,
    atomic_write_text,
    fmt_iso,
    parse_iso,
    sha256_text,
    stable_json,
)

COMMIT_MAX_PAGES = 20
CONTRIBUTOR_MAX_PAGES = 10

STATUS_FAILED = "failed"
STATUS_UNAVAILABLE = "unavailable"
STATUS_TRUNCATED = "truncated"


@dataclass(frozen=True)
class SourceNote:
    source: str
    status: str
    reason: str

    def to_json(self) -> dict[str, str]:
        return {"source": self.source, "status": self.status, "reason": self.reason}

    @classmethod
    def from_json(cls, value: Any) -> SourceNote:
        item = as_dict(value)
        return cls(
            source=as_str(item.get("source"), "unknown"),
            status=as_str(item.get("status"), STATUS_FAILED),
            reason=as_str(item.get("reason"), ""),
        )


@dataclass(frozen=True)
class RepoSnapshot:
    owner: str
    repo: str
    as_of: str
    fetched_at: str
    sha256: str
    notes: tuple[SourceNote, ...]
    data: dict[str, Any]

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def degraded(self) -> bool:
        return any(note.status in (STATUS_FAILED, STATUS_TRUNCATED) for note in self.notes)

    @property
    def degraded_sources(self) -> tuple[str, ...]:
        failed = (
            note.source for note in self.notes if note.status in (STATUS_FAILED, STATUS_TRUNCATED)
        )
        return tuple(sorted(failed))

    def to_json(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "data": self.data,
            "fetched_at": self.fetched_at,
            "notes": [note.to_json() for note in self.notes],
            "owner": self.owner,
            "repo": self.repo,
            "sha256": self.sha256,
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> RepoSnapshot:
        return cls(
            owner=as_str(value.get("owner")),
            repo=as_str(value.get("repo")),
            as_of=as_str(value.get("as_of")),
            fetched_at=as_str(value.get("fetched_at")),
            sha256=as_str(value.get("sha256")),
            notes=tuple(SourceNote.from_json(item) for item in as_list(value.get("notes"))),
            data=as_dict(value.get("data")),
        )


def parse_slug(slug: str) -> tuple[str, str]:
    parts = slug.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise UsageError(f"仓库标识必须是 owner/repo，实际为 {slug!r}")
    return parts[0], parts[1]


def snapshot_path(layout: Layout, owner: str, repo: str, as_of: datetime) -> Path:
    return layout.snapshot_dir(owner, repo) / f"{as_of.strftime('%Y-%m-%d')}.json"


def load_snapshot(layout: Layout, owner: str, repo: str, as_of: datetime) -> RepoSnapshot | None:
    path = snapshot_path(layout, owner, repo, as_of)
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    snapshot = RepoSnapshot.from_json(parsed)
    if snapshot.owner != owner or snapshot.repo != repo:
        return None
    return snapshot


def save_snapshot(layout: Layout, snapshot: RepoSnapshot) -> Path:
    path = snapshot_path(layout, snapshot.owner, snapshot.repo, parse_iso(snapshot.as_of))
    atomic_write_text(path, stable_json(snapshot.to_json()) + "\n")
    return path


def fetch_snapshot(
    client: HttpClient,
    owner: str,
    repo: str,
    *,
    as_of: datetime,
    clock: Clock,
) -> RepoSnapshot:
    """采集并在内存中规范化；落盘由 `save_snapshot` 负责。"""
    notes: list[SourceNote] = []
    base = f"/repos/{owner}/{repo}"

    meta_raw, note = _safe("repo", lambda: client.get_json(base))
    meta = as_dict(meta_raw)
    if not meta:
        reason = note.reason if note is not None else "未知原因"
        raise OsslensError(f"{owner}/{repo} 元数据未获得（{reason}）；这是必需来源，不是可降级项")

    languages_raw, note = _safe("languages", lambda: client.get_json(f"{base}/languages"))
    languages = {str(key): as_int(value) for key, value in as_dict(languages_raw).items()}
    if note is not None:
        notes.append(note)

    contributors_raw, note = _safe(
        "contributors",
        lambda: client.get_pages(f"{base}/contributors", max_pages=CONTRIBUTOR_MAX_PAGES),
    )
    contributors = _normalize_contributors(contributors_raw)
    if note is not None:
        notes.append(note)

    releases_raw, note = _safe(
        "releases", lambda: client.get_pages(f"{base}/releases", max_pages=1)
    )
    releases = _normalize_releases(releases_raw)
    if note is not None:
        notes.append(note)

    since = as_of - timedelta(days=365)
    commits_raw, note = _safe(
        "commits",
        lambda: client.get_pages(
            f"{base}/commits",
            params={"since": fmt_iso(since)},
            max_pages=COMMIT_MAX_PAGES,
        ),
    )
    commits = _normalize_commits(commits_raw)
    if note is not None:
        notes.append(note)

    tree_raw: dict[str, Any] = {}
    default_branch = as_str(meta.get("default_branch"), "main")
    tree_payload, note = _safe(
        "tree",
        lambda: client.get_json(f"{base}/git/trees/{default_branch}", {"recursive": "1"}),
    )
    tree_raw = as_dict(tree_payload)
    if note is not None:
        notes.append(note)
    if as_bool(tree_raw.get("truncated")):
        notes.append(
            SourceNote("tree", STATUS_TRUNCATED, "树超过 GitHub 单次返回上限，结构指标为下界")
        )

    notes.append(
        SourceNote("used_by", STATUS_UNAVAILABLE, "GitHub 无公开 API；L0 标注为未获得，不估算")
    )

    data: dict[str, Any] = {
        "commits": commits,
        "contributors": contributors,
        "languages": languages,
        "releases": releases,
        "repo": _normalize_repo(meta),
        "tree": {
            "entries": _normalize_tree(tree_raw),
            "truncated": as_bool(tree_raw.get("truncated")),
        },
    }
    return RepoSnapshot(
        owner=owner,
        repo=repo,
        as_of=fmt_iso(as_of),
        fetched_at=fmt_iso(clock.now()),
        sha256=sha256_text(stable_json(data)),
        notes=tuple(sorted(notes, key=lambda item: (item.source, item.status, item.reason))),
        data=data,
    )


def _safe(source: str, call: Callable[[], Any]) -> tuple[Any, SourceNote | None]:
    """可选源：失败只降级，不抛（红线：单源失败不影响退出码）。"""
    try:
        return call(), None
    except HttpError as exc:
        return None, SourceNote(source, STATUS_FAILED, f"{exc.status} {exc.reason}")


def _normalize_repo(meta: dict[str, Any]) -> dict[str, Any]:
    license_info = as_dict(meta.get("license"))
    owner_info = as_dict(meta.get("owner"))
    return {
        "archived": as_bool(meta.get("archived")),
        "created_at": as_str(meta.get("created_at")),
        "default_branch": as_str(meta.get("default_branch"), "main"),
        "description": as_str(meta.get("description")),
        "forks": as_int(meta.get("forks_count")),
        "has_issues": as_bool(meta.get("has_issues"), True),
        "homepage": as_str(meta.get("homepage")),
        "language": as_str(meta.get("language")),
        "license": as_str(license_info.get("spdx_id")),
        "open_issues": as_int(meta.get("open_issues_count")),
        "owner_login": as_str(owner_info.get("login")),
        "owner_type": as_str(owner_info.get("type")),
        "pushed_at": as_str(meta.get("pushed_at")),
        "size_kb": as_int(meta.get("size")),
        "stars": as_int(meta.get("stargazers_count")),
        "topics": [as_str(item) for item in as_list(meta.get("topics")) if as_str(item)],
        "watchers": as_int(meta.get("subscribers_count")),
    }


def _normalize_contributors(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in as_list(raw):
        entry = as_dict(item)
        rows.append(
            {
                "contributions": as_int(entry.get("contributions")),
                "login": as_str(as_dict(entry.get("user")).get("login"))
                or as_str(entry.get("login")),
                "type": as_str(entry.get("type"), "User"),
            }
        )
    return sorted(rows, key=lambda row: (-row["contributions"], row["login"]))


def _normalize_releases(raw: Any) -> list[dict[str, Any]]:
    rows = []
    for item in as_list(raw):
        entry = as_dict(item)
        rows.append(
            {
                "draft": as_bool(entry.get("draft")),
                "prerelease": as_bool(entry.get("prerelease")),
                "published_at": as_str(entry.get("published_at")),
                "tag_name": as_str(entry.get("tag_name")),
            }
        )
    return sorted(rows, key=lambda row: (row["published_at"], row["tag_name"]))


def _normalize_commits(raw: Any) -> list[dict[str, Any]]:
    rows = []
    for item in as_list(raw):
        entry = as_dict(item)
        commit = as_dict(entry.get("commit"))
        author = as_dict(commit.get("author"))
        rows.append(
            {
                "date": as_str(author.get("date")),
                "sha": as_str(entry.get("sha")),
            }
        )
    return sorted(rows, key=lambda row: (row["date"], row["sha"]), reverse=True)


def _normalize_tree(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in as_list(raw.get("tree")):
        entry = as_dict(item)
        path = as_str(entry.get("path"))
        if not path:
            continue
        rows.append(
            {
                "path": path,
                "size": as_int(entry.get("size")),
                "type": as_str(entry.get("type")),
            }
        )
    return sorted(rows, key=lambda row: row["path"])
