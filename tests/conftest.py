"""测试公共设施。

★ 这里的快照是**结构化测试数据**，用于验证渲染/打分/时序逻辑；
真实抓取证据由 `pool add / analyze` 对真实仓库的运行提供（见验收报告）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from osslens.collect import RepoSnapshot
from osslens.config import DEFAULT_CONFIG, Layout, _merge
from osslens.util import fmt_iso, sha256_text, stable_json

AS_OF = datetime(2026, 11, 2, tzinfo=UTC)
DEFAULT_CREATED = "2023-01-01T00:00:00Z"


def write_config(root: Path, overrides: dict[str, Any] | None = None) -> Path:
    merged = _merge(DEFAULT_CONFIG, overrides or {}, "config")
    path = root / "config.yaml"
    path.write_text(yaml.safe_dump(merged, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return path


def make_snapshot(
    owner: str = "deepseek-ai",
    repo: str = "DeepEP",
    *,
    as_of: datetime = AS_OF,
    stars: int = 10_000,
    forks: int = 1_000,
    created_at: str = DEFAULT_CREATED,
    pushed_at: str = "2026-10-30T00:00:00Z",
    licenses: str = "MIT",
    commits: list[dict[str, Any]] | None = None,
    contributors: list[dict[str, Any]] | None = None,
    tree: list[dict[str, Any]] | None = None,
    notes: tuple[Any, ...] = (),
) -> RepoSnapshot:
    data: dict[str, Any] = {
        "repo": {
            "archived": False,
            "created_at": created_at,
            "default_branch": "main",
            "description": "test repo",
            "forks": forks,
            "has_issues": True,
            "homepage": "",
            "language": "Python",
            "license": licenses,
            "open_issues": 32,
            "owner_login": owner,
            "owner_type": "Organization",
            "pushed_at": pushed_at,
            "size_kb": 2048,
            "stars": stars,
            "topics": ["llm"],
            "watchers": 100,
        },
        "languages": {"Python": 7500, "Cuda": 2500},
        "contributors": contributors
        or [
            {"contributions": 60, "login": "alice", "type": "User"},
            {"contributions": 40, "login": "bob", "type": "User"},
        ],
        "releases": [
            {
                "draft": False,
                "prerelease": False,
                "published_at": "2026-05-01T00:00:00Z",
                "tag_name": "v1.0",
            }
        ],
        "commits": commits
        or [
            {"date": "2026-10-30T00:00:00Z", "sha": "a" * 40},
            {"date": "2026-09-01T00:00:00Z", "sha": "b" * 40},
        ],
        "tree": {
            "entries": tree
            or [
                {"path": "README.md", "size": 1200, "type": "blob"},
                {"path": "CONTRIBUTING.md", "size": 800, "type": "blob"},
                {"path": "pyproject.toml", "size": 600, "type": "blob"},
                {"path": "deep_ep/__init__.py", "size": 4000, "type": "blob"},
                {"path": "deep_ep/buffer.py", "size": 9000, "type": "blob"},
                {"path": "csrc/main.cu", "size": 20000, "type": "blob"},
            ],
            "truncated": False,
        },
    }
    return RepoSnapshot(
        owner=owner,
        repo=repo,
        as_of=fmt_iso(as_of),
        fetched_at=fmt_iso(as_of),
        sha256=sha256_text(stable_json(data)),
        notes=tuple(notes),
        data=data,
    )


def seed_workspace(
    root: Path, snapshot: RepoSnapshot | None = None, *, overrides: dict[str, Any] | None = None
) -> Path:
    layout = Layout(root)
    layout.ensure_skeleton()
    write_config(root, overrides)
    snap = snapshot or make_snapshot()
    target = layout.snapshot_dir(snap.owner, snap.repo) / f"{snap.as_of[:10]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(snap.to_json(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return root


def read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认清空凭据环境变量；需要凭据的用例自行 setenv。"""
    for name in (
        "GITHUB_TOKEN",
        "OSSLENS_LLM_API_KEY",
        "OSSLENS_LLM_BASE_URL",
        "OSSLENS_LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
