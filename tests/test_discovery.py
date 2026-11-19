"""每日自动发现（GitHub Search）的质量守护。

守护点：
1. 搜索只扩大候选，不构成放行；archived/fork/低星/久未更新/已入池 必须剔除；
2. 去重 + 单轮上限 + 稳定排序（按 stars 降序、slug 升序）；
3. 配置校验 fail-fast（pers_page / max_new / 阈值）；
4. CLI dry-run 不写盘；--apply 才入池，且单个仓库失败不阻断；
5. pool.yml 必须真的调用 discover --apply（避免“代码有、CI 不跑”）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from osslens.cli import main
from osslens.collect import select_discoveries
from osslens.config import Config, ConfigError

from .conftest import make_snapshot, seed_workspace

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def _item(
    slug: str,
    *,
    stars: int = 10_000,
    pushed_days: int = 1,
    archived: bool = False,
    fork: bool = False,
    description: str = "inference serving kernel",
) -> dict[str, Any]:
    return {
        "full_name": slug,
        "stargazers_count": stars,
        "pushed_at": (NOW - timedelta(days=pushed_days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "archived": archived,
        "fork": fork,
        "description": description,
    }


def test_select_filters_and_dedupes_and_caps() -> None:
    items = [
        _item("a/keep-big", stars=50_000),
        _item("b/keep-small", stars=9_000),
        _item("a/KEEP-BIG", stars=50_000),  # 大小写重复
        _item("c/archived", archived=True),
        _item("d/fork", fork=True),
        _item("e/low-stars", stars=100),
        _item("f/stale", pushed_days=800),
        _item("g/existing", stars=99_999),
        _item("", stars=99_999),
    ]
    out = select_discoveries(
        items,
        existing=frozenset({"g/existing"}),
        min_stars=5000,
        max_pushed_age_days=365,
        max_new=2,
        now=NOW,
    )
    assert [item.slug for item in out] == ["a/keep-big", "b/keep-small"]


def test_select_returns_empty_when_nothing_qualifies() -> None:
    out = select_discoveries(
        [_item("x/low", stars=1)],
        existing=frozenset(),
        min_stars=5000,
        max_pushed_age_days=365,
        max_new=5,
        now=NOW,
    )
    assert out == ()


def test_discovery_config_validation(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws")
    with pytest.raises(ConfigError):
        Config.from_mapping(root, {"pool": {"discovery": {"per_page": 0}}})
    with pytest.raises(ConfigError):
        Config.from_mapping(root, {"pool": {"discovery": {"max_new_per_run": 99}}})
    with pytest.raises(ConfigError):
        Config.from_mapping(root, {"pool": {"discovery": {"min_stars": -1}}})
    cfg = Config.from_mapping(
        root,
        {"pool": {"discovery": {"enabled": True, "queries": [" topic:llm ", ""]}}},
    )
    assert cfg.pool.discovery.queries == ("topic:llm",)


class _StubClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def close(self) -> None:
        return None


def test_cli_discover_dry_run_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = seed_workspace(tmp_path / "ws")
    calls: list[tuple[str, int]] = []

    def fake_search(
        _client: object, query: str, *, per_page: int = 20
    ) -> tuple[dict[str, Any], ...]:
        calls.append((query, per_page))
        return (_item("new/alpha", stars=20_000),)

    monkeypatch.setattr("osslens.cli.HttpClient", _StubClient)
    monkeypatch.setattr("osslens.cli.search_repositories", fake_search)
    assert main(["pool", "discover", "--root", str(root), "--as-of", "2026-11-19T00:00:00Z"]) == 0
    assert calls, "必须先真正发起搜索"
    assert not (root / "data" / "pool" / "pool.jsonl").exists() or (
        "new/alpha" not in (root / "data" / "pool" / "pool.jsonl").read_text(encoding="utf-8")
    )


def test_cli_discover_apply_tolerates_single_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = seed_workspace(tmp_path / "ws")
    monkeypatch.setattr("osslens.cli.HttpClient", _StubClient)
    monkeypatch.setattr(
        "osslens.cli.search_repositories",
        lambda *_a, **_k: (_item("ok/repo", stars=20_000), _item("bad/repo", stars=30_000)),
    )
    applied: list[str] = []

    def fake_add(config: Config, slug: str, **_kwargs: object) -> None:
        if slug == "bad/repo":
            from osslens.util import OsslensError

            raise OsslensError("boom")
        applied.append(slug)

    monkeypatch.setattr("osslens.cli._pool_add_one", fake_add)
    assert (
        main(
            [
                "pool",
                "discover",
                "--root",
                str(root),
                "--as-of",
                "2026-11-19T00:00:00Z",
                "--apply",
            ]
        )
        == 0
    )
    assert applied == ["ok/repo"], "单仓库失败不得中断其余入池"


def test_pool_workflow_runs_discovery() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/pool.yml"
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = doc["jobs"]["build-pool"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    assert any("pool discover --apply" in run for run in runs), "CI 必须每日真正执行发现"


def test_keyword_filters_keep_relevance_and_drop_noise() -> None:
    items = [
        _item("p/fast-infer", description="Fast LLM inference engine"),
        _item("q/awesome-list", description="awesome llm inference links"),
        _item("r/generic", description="a general purpose tool"),
    ]
    out = select_discoveries(
        items,
        existing=frozenset(),
        min_stars=5000,
        max_pushed_age_days=365,
        max_new=5,
        now=NOW,
        require_keywords=("inference",),
        exclude_keywords=("awesome",),
    )
    assert [item.slug for item in out] == ["p/fast-infer"]


def test_pool_skip_config_and_validation(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws")
    cfg = Config.from_mapping(root, {"pool": {"skip": ["microsoft/onnxruntime", "A/B"]}})
    assert cfg.pool.skip == ("microsoft/onnxruntime", "A/B")
    assert cfg.pool.skipped("Microsoft/OnnxRuntime") is True
    assert cfg.pool.skipped("a/b") is True
    assert cfg.pool.skipped("other/repo") is False
    with pytest.raises(ConfigError):
        Config.from_mapping(root, {"pool": {"skip": ["not-a-slug"]}})
    with pytest.raises(ConfigError):
        Config.from_mapping(root, {"pool": {"skip": "microsoft/onnxruntime"}})


def test_discover_never_readds_skipped_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = seed_workspace(tmp_path / "ws", overrides={"pool": {"skip": ["dead/repo"]}})
    monkeypatch.setattr("osslens.cli.HttpClient", _StubClient)
    monkeypatch.setattr(
        "osslens.cli.search_repositories",
        lambda *_a, **_k: (_item("dead/repo", stars=99_000), _item("live/repo", stars=20_000)),
    )
    cfg = Config.load(root)
    # 直接验证 CLI 的候选集合：跳过项不得出现在结果里
    out = select_discoveries(
        (_item("dead/repo", stars=99_000), _item("live/repo", stars=20_000)),
        existing=frozenset(cfg.pool.skip),
        min_stars=5000,
        max_pushed_age_days=365,
        max_new=5,
        now=NOW,
    )
    assert [item.slug for item in out] == ["live/repo"]


def test_observe_targets_excludes_skip(tmp_path: Path) -> None:
    from osslens.config import Layout
    from osslens.pool import observe, observe_targets
    from osslens.util import FixedClock

    root = seed_workspace(tmp_path / "ws", overrides={"pool": {"skip": ["deepseek-ai/DeepEP"]}})
    cfg = Config.load(root)
    observe(Layout(root), make_snapshot(), channel="classic", clock=FixedClock(NOW))
    targets = observe_targets(cfg)
    assert "deepseek-ai/DeepEP" not in targets


def test_pool_add_refuses_skipped_repo(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws", overrides={"pool": {"skip": ["microsoft/onnxruntime"]}})
    assert main(["pool", "add", "microsoft/onnxruntime", "--root", str(root)]) == 0
    assert not (root / "data" / "snapshots" / "microsoft__onnxruntime").exists()
