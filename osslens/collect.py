"""GitHub 快照采集（零 LLM）。

设计约束：
- 所有时间来自 `as_of` 或采集时刻，报告不使用 `datetime.now()`。
- 每个可选来源独立降级：单源失败只记 note，不影响退出码（红线 "单源失败不影响退出码"）。
- 快照落盘 + sha256，作为幂等的**输入**：同一 `as_of` 重跑复用同一快照。
"""

from __future__ import annotations

import gzip
import io
import json
import re
import tarfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .config import Config, Layout, SourcesConfig
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
    sha256_bytes,
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
    """读快照；兼容保留期归档后的 ``<date>.json.gz``（内容与 .json 完全一致）。

    归档只改变存放形态，不改内容：真源仍是同一天同一份快照，``--as-of`` 语义不变。
    """
    path = snapshot_path(layout, owner, repo, as_of)
    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
    else:
        packed = path.with_name(path.name + ".gz")
        if not packed.exists():
            return None
        try:
            raw = gzip.decompress(packed.read_bytes()).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    try:
        parsed = json.loads(raw)
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
    packed = path.with_name(path.name + ".gz")
    if packed.exists():
        # 已归档真源：不写第二份未压缩副本（同一天同一份快照，避免真源双份漂移）
        return packed
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


# --------------------------------------------------------------------------- 源码采集


TEXT_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cmake",
        ".cpp",
        ".cu",
        ".cuh",
        ".go",
        ".h",
        ".hpp",
        ".md",
        ".py",
        ".rs",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
TEXT_NAMES = frozenset({"CMakeLists.txt", "Makefile", "Dockerfile"})
ENTRYPOINT_NAMES = frozenset(
    {
        "__init__.py",
        "__main__.py",
        "app.py",
        "cli.py",
        "index.ts",
        "main.cu",
        "main.go",
        "main.py",
        "main.rs",
    }
)


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class SourceBundle:
    """一次 commit 的源码切片（只取证据所需文件，不搬整仓）。"""

    commit: str
    tarball_sha256: str
    files: tuple[SourceFile, ...]
    root: Path

    def read(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8", errors="replace")

    def texts(self) -> list[tuple[SourceFile, str]]:
        return [(item, self.read(item.path)) for item in self.files]


def sources_root(layout: Layout, owner: str, repo: str, as_of: datetime) -> Path:
    return layout.snapshot_dir(owner, repo) / as_of.strftime("%Y-%m-%d") / "src"


def load_sources(
    layout: Layout, owner: str, repo: str, as_of: datetime, commit: str
) -> SourceBundle | None:
    root = sources_root(layout, owner, repo, as_of)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if as_str(payload.get("commit")) != commit:
        return None
    files_list: list[SourceFile] = []
    for item in as_list(payload.get("files")):
        row = as_dict(item)
        path = as_str(row.get("path"))
        if not path:
            continue
        files_list.append(
            SourceFile(
                path=path,
                sha256=as_str(row.get("sha256")),
                size=as_int(row.get("size")),
            )
        )
    files = tuple(files_list)
    return SourceBundle(
        commit=commit,
        tarball_sha256=as_str(payload.get("tarball_sha256")),
        files=files,
        root=root,
    )


def fetch_sources(
    config: Config,
    layout: Layout,
    owner: str,
    repo: str,
    *,
    commit: str,
    as_of: datetime,
) -> SourceBundle:
    """下载 `<commit>` 的 tarball（1 次请求，不占 API 额度），按需切片落盘。

    同一 commit 的源码不可变 → 与 `--as-of` 绑定的切片可复用，保证幂等。
    """
    cached = load_sources(layout, owner, repo, as_of, commit)
    if cached is not None:
        return cached

    url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/{commit}"
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "osslens/0.1"})
    if response.status_code != 200:
        raise HttpError(url, response.status_code, "源码包下载失败")
    data = response.content

    selected = _select_sources(data, config.sources)
    root = sources_root(layout, owner, repo, as_of)
    files: list[SourceFile] = []
    for path, raw in selected:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files.append(SourceFile(path=path, sha256=sha256_bytes(raw), size=len(raw)))

    manifest = {
        "commit": commit,
        "tarball_sha256": sha256_bytes(data),
        "files": [{"path": item.path, "sha256": item.sha256, "size": item.size} for item in files],
    }
    atomic_write_text(root / "manifest.json", stable_json(manifest) + "\n")
    return SourceBundle(
        commit=commit, tarball_sha256=sha256_bytes(data), files=tuple(files), root=root
    )


def _select_sources(data: bytes, limits: SourcesConfig) -> list[tuple[str, bytes]]:
    """按「README → 入口文件 → 大文件优先」确定性选片，带三重上限。"""
    candidates: list[tuple[int, int, str, bytes]] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or member.size <= 0:
                continue
            name = member.name.split("/", 1)[-1] if "/" in member.name else member.name
            if not name or name.startswith("/") or ".." in Path(name).parts:
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in TEXT_SUFFIXES and Path(name).name not in TEXT_NAMES:
                continue
            if member.size > limits.max_file_bytes:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            payload = extracted.read()
            base = Path(name).name.lower()
            if base.startswith("readme"):
                priority = 0
            elif base in ENTRYPOINT_NAMES:
                priority = 1
            else:
                priority = 2
            candidates.append((priority, -member.size, name, payload))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    selected: list[tuple[str, bytes]] = []
    total = 0
    for _priority, _neg_size, name, payload in candidates:
        if len(selected) >= limits.max_files:
            break
        if total + len(payload) > limits.max_total_bytes:
            continue
        selected.append((name, payload))
        total += len(payload)
    return sorted(selected, key=lambda item: item[0])


# --------------------------------------------------------------------------- 外部资料探测


STATUS_HIT = "hit"
STATUS_MISS = "miss"
STATUS_BLOCKED = "blocked"
STATUS_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ExternalProbe:
    """外部资料判定结果。四元组 + 判定，原文另存（结构分离）。"""

    source: str
    url: str
    status: str
    reason: str
    fetched_at: str
    sha256: str
    paths_found: int
    raw_relpath: str

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "url": self.url,
            "status": self.status,
            "reason": self.reason,
            "fetched_at": self.fetched_at,
            "sha256": self.sha256,
            "paths_found": self.paths_found,
            "raw_relpath": self.raw_relpath,
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> ExternalProbe:
        return cls(
            source=as_str(value.get("source"), "deepwiki"),
            url=as_str(value.get("url")),
            status=as_str(value.get("status"), STATUS_UNAVAILABLE),
            reason=as_str(value.get("reason")),
            fetched_at=as_str(value.get("fetched_at")),
            sha256=as_str(value.get("sha256")),
            paths_found=as_int(value.get("paths_found")),
            raw_relpath=as_str(value.get("raw_relpath")),
        )


def external_dir(layout: Layout, owner: str, repo: str, as_of: datetime) -> Path:
    return layout.snapshot_dir(owner, repo) / as_of.strftime("%Y-%m-%d") / "external"


def probe_external(
    config: Config,
    layout: Layout,
    owner: str,
    repo: str,
    *,
    as_of: datetime,
    clock: Clock,
    repo_paths: Sequence[str],
) -> ExternalProbe:
    """DeepWiki 探测器：**fail-closed**，只看正文是否含 ≥N 个仓库内真实路径。

    传输默认走官方 MCP（`read_wiki_contents`，正文含真实路径）；HTML 抓取作为备选。
    不因 HTTP 200 判命中；不因页面能打开就认为已索引；未命中绝不生成模板化页面。
    """
    directory = external_dir(layout, owner, repo, as_of)
    meta_path = directory / "deepwiki.json"
    if meta_path.exists():
        try:
            return ExternalProbe.from_json(json.loads(meta_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass

    url = f"{config.external.deepwiki_base_url.rstrip('/')}/{owner}/{repo}"
    if not config.external.deepwiki_enabled:
        disabled = ExternalProbe(
            "deepwiki", url, STATUS_UNAVAILABLE, "已在配置中禁用", "", "", 0, ""
        )
        return _save_probe(directory, disabled)

    text, failure, reason = _fetch_external(config, owner, repo)
    if failure:
        return _save_probe(
            directory, ExternalProbe("deepwiki", url, failure, reason, "", "", 0, "")
        )

    stamp = fmt_iso(clock.now())
    raw_sha = sha256_text(text)
    raw_relpath = "source.txt"
    status, found = judge_external(
        text, repo_paths=repo_paths, min_paths=config.external.min_repo_paths
    )
    threshold = config.external.min_repo_paths
    if status == STATUS_HIT:
        reason = f"正文含 {found} 个仓库内真实路径（阈值 {threshold}）"
    else:
        reason = f"正文仅含 {found} 个仓库内真实路径（阈值 {threshold}）→ 视为未索引/模板页"
    probe = ExternalProbe("deepwiki", url, status, reason, stamp, raw_sha, found, raw_relpath)
    return _save_probe(directory, probe, text)


def _fetch_external(config: Config, owner: str, repo: str) -> tuple[str, str, str]:
    """返回 `(正文, 失败状态, 原因)`；成功时后两项为空。"""
    transport = config.external.deepwiki_transport
    if transport in ("mcp", "auto"):
        text, failure, reason = _fetch_deepwiki_mcp(config, owner, repo)
        if text or transport == "mcp":
            return text, failure, reason
    return _fetch_deepwiki_html(config, owner, repo)


def _fetch_deepwiki_mcp(config: Config, owner: str, repo: str) -> tuple[str, str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=config.external.timeout_seconds) as client:
            init = client.post(
                config.external.deepwiki_mcp_url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "osslens", "version": "0.1"},
                    },
                },
            )
            if init.status_code != 200:
                return "", STATUS_UNAVAILABLE, f"MCP 初始化 HTTP {init.status_code}"
            session = init.headers.get("mcp-session-id")
            session_headers = dict(headers)
            if session:
                session_headers["mcp-session-id"] = session
            client.post(
                config.external.deepwiki_mcp_url,
                headers=session_headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            response = client.post(
                config.external.deepwiki_mcp_url,
                headers=session_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "read_wiki_contents",
                        "arguments": {"repoName": f"{owner}/{repo}"},
                    },
                },
            )
    except httpx.HTTPError as exc:
        return "", STATUS_UNAVAILABLE, f"MCP 网络错误：{type(exc).__name__}"

    payload = _rpc_payload(response.text)
    if payload is None:
        return "", STATUS_UNAVAILABLE, f"MCP 响应不可解析（HTTP {response.status_code}）"
    error = payload.get("error")
    if isinstance(error, dict):
        message = as_str(error.get("message"), "未知错误")
        return "", STATUS_MISS, f"MCP 返回错误：{message}"
    result = as_dict(payload.get("result"))
    if as_bool(result.get("isError")):
        return "", STATUS_MISS, "MCP 报告该仓库无可用 wiki"
    chunks = [
        as_str(as_dict(item).get("text"))
        for item in as_list(result.get("content"))
        if as_str(as_dict(item).get("text"))
    ]
    text = "\n".join(chunks)
    if not text:
        return "", STATUS_MISS, "MCP 返回空正文"
    return text, "", ""


def _rpc_payload(raw: str) -> dict[str, Any] | None:
    """兼容 SSE（`data: {...}`）与纯 JSON 两种响应。"""
    for line in raw.splitlines():
        if line.startswith("data:"):
            try:
                return as_dict(json.loads(line[5:].strip()))
            except json.JSONDecodeError:
                continue
    try:
        return as_dict(json.loads(raw))
    except json.JSONDecodeError:
        return None


def _fetch_deepwiki_html(config: Config, owner: str, repo: str) -> tuple[str, str, str]:
    url = f"{config.external.deepwiki_base_url.rstrip('/')}/{owner}/{repo}"
    try:
        with httpx.Client(timeout=config.external.timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "Mozilla/5.0 (osslens/0.1)"})
    except httpx.HTTPError as exc:
        return "", STATUS_UNAVAILABLE, f"网络错误：{type(exc).__name__}"

    raw = response.text
    if response.status_code == 429 or "Security Checkpoint" in raw:
        return "", STATUS_BLOCKED, f"HTTP {response.status_code} 安全校验页（Vercel checkpoint）"
    if response.status_code >= 400:
        return "", STATUS_UNAVAILABLE, f"HTTP {response.status_code}"
    return _visible_text(raw), "", ""


def judge_external(raw: str, *, repo_paths: Sequence[str], min_paths: int) -> tuple[str, int]:
    """判定只看「正文是否含仓库内真实路径」——不看 HTTP 状态、不看页面能否打开。

    这是红线 #4 的可测试内核：模板页（有仓库名、无路径）必然判 miss。
    """
    visible = _visible_text(raw)
    found = sum(1 for path in dict.fromkeys(repo_paths) if len(path) >= 8 and path in visible)
    return (STATUS_HIT if found >= min_paths else STATUS_MISS), found


def _save_probe(directory: Path, probe: ExternalProbe, raw: str = "") -> ExternalProbe:
    """原文与判定元数据**结构分离**（红线 #13）。"""
    if raw:
        atomic_write_text(directory / probe.raw_relpath, raw)
    atomic_write_text(directory / "deepwiki.json", stable_json(probe.to_json()) + "\n")
    return probe


def _visible_text(raw: str) -> str:
    import html as html_module

    without_scripts = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    stripped = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html_module.unescape(stripped))


# --------------------------------------------------------------------------- 自动发现（Search）


@dataclass(frozen=True)
class DiscoveryCandidate:
    """搜索命中且通过本地过滤的候选仓库（尚未入池，未进入放行判定）。"""

    slug: str
    stars: int
    pushed_at: str
    description: str


def search_repositories(
    client: HttpClient, query: str, *, per_page: int = 20
) -> tuple[dict[str, Any], ...]:
    """调用 GitHub Search API（`/search/repositories`），返回原始 items（零 LLM）。

    只做一次请求：分页留给后续版本；`per_page` 上限 100 由配置层校验。
    """
    payload = client.get_json(
        "/search/repositories",
        {"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
    )
    return tuple(as_dict(item) for item in as_list(as_dict(payload).get("items")))


def select_discoveries(
    items: Sequence[dict[str, Any]],
    *,
    existing: frozenset[str],
    min_stars: int,
    max_pushed_age_days: int,
    max_new: int,
    now: datetime,
    require_keywords: Sequence[str] = (),
    exclude_keywords: Sequence[str] = (),
) -> tuple[DiscoveryCandidate, ...]:
    """把搜索命中过滤成候选：archived/fork/低星/久未更新/已入池 全部剔除。

    搜索排序只用于“先看谁”，**不构成放行**；放行仍由 hot/classic 门槛决定。
    """
    cutoff = now - timedelta(days=max_pushed_age_days)
    picked: dict[str, DiscoveryCandidate] = {}
    for item in items:
        slug = as_str(item.get("full_name")).strip()
        owner, _, repo = slug.partition("/")
        if not owner or not repo:
            continue
        key = slug.lower()
        if key in existing:
            continue
        if as_bool(item.get("archived")) or as_bool(item.get("fork")):
            continue
        description = as_str(item.get("description")).strip()
        haystack = f"{slug} {description}".lower()
        if require_keywords and not any(word in haystack for word in require_keywords):
            continue
        if exclude_keywords and any(word in haystack for word in exclude_keywords):
            continue
        stars = as_int(item.get("stargazers_count"))
        if stars < min_stars:
            continue
        pushed = as_str(item.get("pushed_at"))
        try:
            pushed_at = parse_iso(pushed)
        except ValueError:
            continue
        if pushed_at < cutoff:
            continue
        picked.setdefault(
            key,
            DiscoveryCandidate(
                slug=f"{owner}/{repo}",
                stars=stars,
                pushed_at=pushed,
                description=description,
            ),
        )
    ordered = sorted(picked.values(), key=lambda item: (-item.stars, item.slug.lower()))
    return tuple(ordered[: max(0, max_new)])
