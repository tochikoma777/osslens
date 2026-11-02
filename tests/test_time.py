"""跨天 / 跨周 / 跨月时序（红线 #20：时间驱动逻辑必须写受控时钟单测）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from osslens.cli import main
from osslens.collect import save_snapshot
from osslens.config import Config
from osslens.depth import CostEvent, compute_quota

from .conftest import make_snapshot, seed_workspace

SUNDAY = datetime(2026, 11, 1, 9, tzinfo=UTC)
MONDAY = datetime(2026, 11, 2, 9, tzinfo=UTC)


def _event(as_of: datetime, *, depth: str = "strong", tokens: int = 1000) -> CostEvent:
    return CostEvent(
        event="call",
        repo="deepseek-ai/DeepEP",
        depth=depth,
        model="m",
        prompt_tokens=tokens,
        completion_tokens=0,
        estimated_cost=0.0,
        source="api",
        as_of=as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        run_id="r",
        requested_depth=depth,
        actual_depth=depth,
        reason="baseline",
    )


def test_week_boundary_resets_quota(tmp_path: Path) -> None:
    """周日与周一属于不同配额周：周日晚的 strong 不计入新一周。"""
    config = Config.from_mapping(tmp_path)
    quota = compute_quota(config, [_event(SUNDAY), _event(MONDAY)], MONDAY)
    assert quota.week_start == "2026-11-02"
    assert quota.strong_used == 1, "只有周一的调用计入本周"
    assert quota.tokens_week == 1000


def test_previous_week_not_counted(tmp_path: Path) -> None:
    config = Config.from_mapping(tmp_path)
    quota = compute_quota(config, [_event(SUNDAY)], MONDAY)
    assert quota.strong_used == 0
    assert quota.tokens_week == 0
    assert quota.tokens_month == 1000, "同月仍计入月度预算"


def test_month_boundary_is_separate_window(tmp_path: Path) -> None:
    config = Config.from_mapping(tmp_path)
    october = datetime(2026, 10, 31, 9, tzinfo=UTC)
    quota = compute_quota(config, [_event(october)], MONDAY)
    assert quota.month_start == "2026-11-01"
    assert quota.tokens_month == 0


def test_report_rerun_across_days_only_moves_time_fields(tmp_path: Path) -> None:
    """同一份内容、不同 as-of：差异只能落在时间字段，不能漂到别处。"""
    day1 = datetime(2026, 11, 2, tzinfo=UTC)
    root = seed_workspace(tmp_path / "ws", make_snapshot(as_of=day1))
    layout = Config.load(root).layout

    save_snapshot(layout, make_snapshot(as_of=day1 + timedelta(days=1)))
    assert (
        main(
            [
                "analyze",
                "deepseek-ai/DeepEP",
                "--root",
                str(root),
                "--as-of",
                "2026-11-02T00:00:00Z",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "analyze",
                "deepseek-ai/DeepEP",
                "--root",
                str(root),
                "--as-of",
                "2026-11-03T00:00:00Z",
            ]
        )
        == 0
    )

    first = (
        (root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    second = (
        (root / "reports" / "deepseek-ai__DeepEP__2026-11-03.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(first) == len(second)
    diffs = [(a, b) for a, b in zip(first, second, strict=True) if a != b]
    assert diffs, "两天报告应至少时间字段不同"
    # 允许的时间派生字段只有三类：as-of、距今天数、项目年龄
    time_fields = ("as-of", "距今天数", "项目年龄")
    for left, right in diffs:
        assert any(field in left and field in right for field in time_fields), (
            f"意外差异：{left!r} vs {right!r}"
        )
