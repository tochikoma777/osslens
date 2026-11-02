"""候选池：去重、分通道、观察期、跨天时序。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from osslens.cli import main
from osslens.config import Config, Layout
from osslens.pool import evaluate_eligibility, load_series, observe, score_channel
from osslens.util import FixedClock

from .conftest import make_snapshot, read_jsonl_file, write_config

DAY_ZERO = datetime(2026, 11, 1, tzinfo=UTC)


def _layout(root: Path) -> Layout:
    layout = Layout(root)
    layout.ensure_skeleton()
    return layout


def test_repeat_add_appends_observation_not_entry(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    first = make_snapshot(stars=1000, as_of=DAY_ZERO)
    observe(layout, first, channel="classic", clock=FixedClock(DAY_ZERO))
    observe(layout, first, channel="classic", clock=FixedClock(DAY_ZERO + timedelta(days=1)))

    records = read_jsonl_file(layout.pool_jsonl)
    assert len(records) == 2, "append-only：两次入池 = 两条观测事件"
    series = load_series(layout)
    assert len(series) == 1, "同一 repo 不产生第二条条目"
    assert series[0].observed_days == 2


def test_channels_are_scored_separately(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    layout = _layout(root)
    observe(
        layout,
        make_snapshot(repo="HotRepo", stars=9000),
        channel="hot",
        clock=FixedClock(DAY_ZERO),
    )
    observe(
        layout,
        make_snapshot(repo="ClassicRepo", stars=9000),
        channel="classic",
        clock=FixedClock(DAY_ZERO),
    )
    series = load_series(layout)
    hot_rows = score_channel(config, series, channel="hot", as_of=DAY_ZERO)
    classic_rows = score_channel(config, series, channel="classic", as_of=DAY_ZERO)
    assert [row.repo for row in hot_rows] == ["deepseek-ai/HotRepo"]
    assert [row.repo for row in classic_rows] == ["deepseek-ai/ClassicRepo"]


def test_delta_requires_two_observations(tmp_path: Path) -> None:
    """观测不足 2 次 → delta 为 0，不估算（§6.1）。"""
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    layout = _layout(root)
    observe(
        layout,
        make_snapshot(stars=5000),
        channel="hot",
        clock=FixedClock(DAY_ZERO),
    )
    rows = evaluate_eligibility(config, load_series(layout), as_of=DAY_ZERO + timedelta(days=9))
    assert rows[0].eligible is False
    assert "增量 0" in rows[0].reason


def test_hot_observe_period_blocks_then_allows(tmp_path: Path) -> None:
    """受控时钟跨天推进：第 6 天排除（观察期未满），第 7 天放行。"""
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    layout = _layout(root)

    clock = FixedClock(DAY_ZERO)
    observe(layout, make_snapshot(stars=1000, as_of=DAY_ZERO), channel="hot", clock=clock)
    clock.advance(days=1)
    observe(layout, make_snapshot(stars=1300, as_of=clock.now()), channel="hot", clock=clock)

    series = load_series(layout)

    day6 = evaluate_eligibility(config, series, as_of=DAY_ZERO + timedelta(days=6))
    assert day6[0].eligible is False
    assert "观察期未满" in day6[0].reason
    assert "还差 1 天" in day6[0].reason

    clock.advance(days=1)  # 第 7 天
    day7 = evaluate_eligibility(config, series, as_of=DAY_ZERO + timedelta(days=7))
    assert day7[0].eligible is True
    assert "观察期已满" in day7[0].reason


def test_classic_requires_stars_and_age(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    layout = _layout(root)
    observe(
        layout,
        make_snapshot(stars=6000, created_at="2025-01-01T00:00:00Z"),
        channel="classic",
        clock=FixedClock(DAY_ZERO),
    )
    rows = evaluate_eligibility(config, load_series(layout), as_of=DAY_ZERO)
    assert rows[0].eligible is False
    assert "年龄" in rows[0].reason


def test_watchlist_is_intent_layer_not_filter(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    config = Config.from_mapping(root, {"watchlist": ["deepseek-ai/DeepEP"]})
    layout = _layout(root)
    observe(
        layout,
        make_snapshot(stars=10),
        channel="watchlist",
        clock=FixedClock(DAY_ZERO),
    )
    rows = evaluate_eligibility(config, load_series(layout), as_of=DAY_ZERO)
    assert rows[0].eligible is True
    assert "意图层" in rows[0].reason


def test_pool_list_prints_channels_separately(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "ws"
    layout = _layout(root)
    write_config(root)
    observe(layout, make_snapshot(repo="HotRepo"), channel="hot", clock=FixedClock(DAY_ZERO))
    observe(
        layout, make_snapshot(repo="ClassicRepo"), channel="classic", clock=FixedClock(DAY_ZERO)
    )
    assert main(["pool", "list", "--root", str(root)]) == 0
    output = capsys.readouterr().out
    assert "通道 hot" in output
    assert "通道 classic" in output
    assert output.index("通道 hot") < output.index("通道 classic")
