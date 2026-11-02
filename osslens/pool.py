"""候选池：append-only 观测序列、去重、分通道打分、观察期判定。

★ 两个通道分别排序，分数不可跨通道比较（设计方案 §6.1）。
★ 分数只用于排序，绝不用于升档（§6.2 / 红线 #12）——本模块不返回任何档位。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .collect import RepoSnapshot
from .config import Config, Layout
from .util import (
    Clock,
    append_jsonl,
    as_int,
    as_str,
    days_between,
    fmt_iso,
    parse_iso,
    r4,
    read_jsonl,
    start_of_day,
    zscore,
)

OBSERVATION_KIND = "observation"
HOT = "hot"
CLASSIC = "classic"
WATCHLIST = "watchlist"
CHANNELS = (HOT, CLASSIC, WATCHLIST)


@dataclass(frozen=True)
class Observation:
    repo: str
    channel: str
    observed_at: datetime
    snapshot_date: str
    stars: int
    forks: int
    created_at: str
    sha256: str
    degraded: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": OBSERVATION_KIND,
            "repo": self.repo,
            "channel": self.channel,
            "observed_at": fmt_iso(self.observed_at),
            "snapshot_date": self.snapshot_date,
            "stars": self.stars,
            "forks": self.forks,
            "created_at": self.created_at,
            "sha256": self.sha256,
            "degraded": list(self.degraded),
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> Observation:
        return cls(
            repo=as_str(value.get("repo")),
            channel=as_str(value.get("channel"), CLASSIC),
            observed_at=parse_iso(as_str(value.get("observed_at"), "1970-01-01T00:00:00Z")),
            snapshot_date=as_str(value.get("snapshot_date")),
            stars=as_int(value.get("stars")),
            forks=as_int(value.get("forks")),
            created_at=as_str(value.get("created_at")),
            sha256=as_str(value.get("sha256")),
            degraded=tuple(sorted(as_str(item) for item in value.get("degraded", []) if item)),
        )


@dataclass(frozen=True)
class RepoSeries:
    repo: str
    channel: str
    observations: tuple[Observation, ...]

    @property
    def latest(self) -> Observation:
        return self.observations[-1]

    @property
    def first_observed_at(self) -> datetime:
        return self.observations[0].observed_at

    @property
    def observed_days(self) -> int:
        return len(self.observations)


@dataclass(frozen=True)
class ScoreRow:
    repo: str
    channel: str
    score: float
    observations: int
    metrics: dict[str, float]


@dataclass(frozen=True)
class EligibilityRow:
    repo: str
    channel: str
    eligible: bool
    reason: str
    score: float


def observe(layout: Layout, snapshot: RepoSnapshot, *, channel: str, clock: Clock) -> Observation:
    """追加一条观测——**永远追加，永不覆盖**（红线 #6）。"""
    repo_meta = snapshot.data.get("repo", {})
    observation = Observation(
        repo=snapshot.slug,
        channel=channel,
        observed_at=clock.now(),
        snapshot_date=snapshot.as_of[:10],
        stars=as_int(repo_meta.get("stars")),
        forks=as_int(repo_meta.get("forks")),
        created_at=as_str(repo_meta.get("created_at")),
        sha256=snapshot.sha256,
        degraded=snapshot.degraded_sources,
    )
    append_jsonl(layout.pool_jsonl, observation.to_json())
    return observation


def load_series(layout: Layout) -> list[RepoSeries]:
    """把 append-only 事件流折叠成 (repo, channel) 序列；去重在此完成。

    去重语义：同一 repo 重复入池**不新增条目**，只让序列变长。
    """
    grouped: dict[tuple[str, str], list[Observation]] = {}
    for record in read_jsonl(layout.pool_jsonl):
        if as_str(record.get("kind")) != OBSERVATION_KIND:
            continue
        observation = Observation.from_json(record)
        if not observation.repo:
            continue
        grouped.setdefault((observation.repo, observation.channel), []).append(observation)
    series = [
        RepoSeries(
            repo=repo,
            channel=channel,
            observations=tuple(sorted(items, key=lambda item: (item.observed_at, item.sha256))),
        )
        for (repo, channel), items in grouped.items()
    ]
    return sorted(series, key=lambda item: (item.channel, item.repo))


def score_channel(
    config: Config, series: list[RepoSeries], *, channel: str, as_of: datetime
) -> list[ScoreRow]:
    rows = [item for item in series if item.channel == channel]
    if not rows:
        return []

    raw: list[dict[str, float]] = []
    for item in rows:
        if channel == HOT:
            raw.append(
                {
                    "star_delta_7d": float(_delta(item, as_of, field="stars")),
                    "stars": float(item.latest.stars),
                    "fork_delta_7d": float(_delta(item, as_of, field="forks")),
                }
            )
        else:
            raw.append(
                {
                    "stars": float(item.latest.stars),
                    "observations": float(len(item.observations)),
                }
            )

    weights = config.score.hot if channel == HOT else config.score.classic
    keys = sorted(weights)
    z_columns = {key: zscore([row[key] for row in raw]) for key in keys}
    scored: list[ScoreRow] = []
    for index, item in enumerate(rows):
        score = sum(weights[key] * z_columns[key][index] for key in keys)
        scored.append(
            ScoreRow(
                repo=item.repo,
                channel=channel,
                score=r4(score),
                observations=len(item.observations),
                metrics={key: r4(raw[index][key]) for key in keys},
            )
        )
    return sorted(scored, key=lambda row: (-row.score, row.repo))


def evaluate_eligibility(
    config: Config, series: list[RepoSeries], *, as_of: datetime
) -> list[EligibilityRow]:
    scores: dict[tuple[str, str], float] = {}
    for channel in sorted({item.channel for item in series}):
        for row in score_channel(config, series, channel=channel, as_of=as_of):
            scores[(row.channel, row.repo)] = row.score

    rows: list[EligibilityRow] = []
    for item in series:
        score = scores.get((item.channel, item.repo), 0.0)
        if item.channel == HOT:
            delta = _delta(item, as_of, field="stars")
            observed = days_between(as_of, item.first_observed_at)
            # 观察期先判：未满观察期的增量不可信，先让它跑几天（§6.3）
            if observed < config.pool.hot_observe_days:
                remain = config.pool.hot_observe_days - observed
                rows.append(
                    EligibilityRow(
                        item.repo,
                        item.channel,
                        False,
                        f"观察期未满：已观测 {observed} 天，还差 {remain} 天",
                        score,
                    )
                )
            elif delta < config.pool.hot_min_star_delta_7d:
                rows.append(
                    EligibilityRow(
                        item.repo,
                        item.channel,
                        False,
                        f"7 日 star 增量 {delta} < 门槛 {config.pool.hot_min_star_delta_7d}",
                        score,
                    )
                )
            else:
                rows.append(
                    EligibilityRow(
                        item.repo,
                        item.channel,
                        True,
                        f"7 日 star 增量 {delta} ≥ 门槛，观察期已满 {observed} 天",
                        score,
                    )
                )
        elif item.channel == CLASSIC:
            stars = item.latest.stars
            age = (
                days_between(as_of, parse_iso(item.latest.created_at))
                if item.latest.created_at
                else -1
            )
            if stars < config.pool.classic_min_stars:
                rows.append(
                    EligibilityRow(
                        item.repo,
                        item.channel,
                        False,
                        f"star {stars} < 门槛 {config.pool.classic_min_stars}",
                        score,
                    )
                )
            elif age < config.pool.classic_min_age_days:
                rows.append(
                    EligibilityRow(
                        item.repo,
                        item.channel,
                        False,
                        f"仓库年龄 {age} 天 < 门槛 {config.pool.classic_min_age_days} 天",
                        score,
                    )
                )
            else:
                rows.append(
                    EligibilityRow(
                        item.repo, item.channel, True, f"star {stars} ≥ 门槛，年龄 {age} 天", score
                    )
                )
        else:
            rows.append(
                EligibilityRow(
                    item.repo, item.channel, True, "watchlist 为意图层：直接进入深挖候选", score
                )
            )
    return sorted(rows, key=lambda row: (row.channel, not row.eligible, -row.score, row.repo))


def _delta(item: RepoSeries, as_of: datetime, *, field: str) -> int:
    """末次 − 7 日窗口起点；窗口内观测 <2 次返回 0（§6.1：不估算、不外推）。"""
    window_start = start_of_day(as_of) - timedelta(days=7)
    window = [obs for obs in item.observations if window_start <= obs.observed_at <= as_of]
    if len(window) < 2:
        return 0
    return int(getattr(window[-1], field) - getattr(window[0], field))
