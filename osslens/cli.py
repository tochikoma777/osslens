"""命令行入口：参数解析 / 子命令分发 / 退出码兜底。

退出码契约（写死）：0 完成（可能已降级）· 1 配置或真错误 · 2 参数错误。
可选源失败、配额耗尽、预算拦截、未配 key 一律 **0**。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .collect import RepoSnapshot, fetch_snapshot, load_snapshot, parse_slug, save_snapshot
from .config import CONFIG_TEMPLATE, Config, Layout
from .depth import (
    REQUESTED_DEPTHS,
    build_ledger_event,
    load_events,
    record_event,
    resolve_depth,
    summarize,
)
from .featcard import build_featcard
from .pool import (
    CHANNELS,
    CLASSIC,
    WATCHLIST,
    evaluate_eligibility,
    load_series,
    observe,
    score_channel,
)
from .render import ReportInputs, render_report
from .util import (
    Clock,
    ConfigError,
    FixedClock,
    HttpClient,
    OsslensError,
    SystemClock,
    UsageError,
    atomic_write_text,
    fmt_date,
    fmt_iso,
    parse_iso,
    stable_json,
)

# L0 尚未接入任何 LLM 档位；L1 起改为按真实可用性判断。
LLM_AVAILABLE = False

SEED_PATTERNS = """\
# 规律库种子（L3 起使用）。每条必须带反例位（红线 #11：无反例位的条目禁止入库）。
# 格式见执行手册 附录 B。
[]
"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.handler(args))
    except UsageError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except OsslensError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------- 解析器


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m osslens",
        description="低成本、可长期运行的开源项目深度分析系统（L0：零 LLM 体检）",
    )
    parser.add_argument("--version", action="version", version=f"osslens {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="工作区根目录（默认当前目录）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", parents=[common], help="初始化工作区骨架")
    init_parser.set_defaults(handler=_cmd_init)

    pool_parser = sub.add_parser("pool", parents=[common], help="候选池（零 LLM）")
    pool_sub = pool_parser.add_subparsers(dest="pool_command", required=True)

    add_parser = pool_sub.add_parser("add", parents=[common], help="抓取快照并追加观测")
    add_parser.add_argument("slug", help="owner/repo")
    add_parser.add_argument("--channel", choices=CHANNELS, default=None)
    add_parser.add_argument("--as-of", dest="as_of", default=None, help="ISO8601 观测基准时间")
    add_parser.set_defaults(handler=_cmd_pool_add)

    list_parser = pool_sub.add_parser("list", parents=[common], help="按通道分别打分排序")
    list_parser.add_argument("--as-of", dest="as_of", default=None)
    list_parser.add_argument("--json", action="store_true", help="输出稳定 JSON")
    list_parser.set_defaults(handler=_cmd_pool_list)

    eligible_parser = pool_sub.add_parser(
        "eligible", parents=[common], help="深挖候选（含观察期判定）"
    )
    eligible_parser.add_argument("--as-of", dest="as_of", default=None)
    eligible_parser.add_argument("--json", action="store_true")
    eligible_parser.set_defaults(handler=_cmd_pool_eligible)

    analyze_parser = sub.add_parser("analyze", parents=[common], help="产出体检报告")
    analyze_parser.add_argument("slug", help="owner/repo")
    analyze_parser.add_argument("--depth", choices=REQUESTED_DEPTHS, default="auto")
    analyze_parser.add_argument("--channel", choices=CHANNELS, default=None)
    analyze_parser.add_argument("--domain", default="未指定")
    analyze_parser.add_argument("--as-of", dest="as_of", default=None)
    analyze_parser.add_argument("--dry-run", action="store_true", help="只打印决策，不落盘")
    analyze_parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="跳过非降级台账；降级事件永不跳过（红线 #10）",
    )
    analyze_parser.set_defaults(handler=_cmd_analyze)

    cost_parser = sub.add_parser("cost", parents=[common], help="成本台账")
    cost_parser.add_argument("--as-of", dest="as_of", default=None)
    cost_parser.add_argument("--json", action="store_true")
    cost_parser.set_defaults(handler=_cmd_cost)

    return parser


# --------------------------------------------------------------------------- 子命令


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    layout = Layout(root)
    layout.ensure_skeleton()
    created: list[str] = []
    skipped: list[str] = []

    if layout.config_file.exists():
        skipped.append("config.yaml")
    else:
        atomic_write_text(layout.config_file, CONFIG_TEMPLATE)
        created.append("config.yaml")

    if layout.seed_patterns.exists():
        skipped.append("patterns/seed.yaml")
    else:
        atomic_write_text(layout.seed_patterns, SEED_PATTERNS)
        created.append("patterns/seed.yaml")

    for path in (
        "data/ledger/",
        "data/pool/",
        "data/snapshots/",
        "data/featcards/",
        "data/costs/",
        "reports/",
    ):
        (root / path).mkdir(parents=True, exist_ok=True)
        created.append(path)

    print(f"工作区：{root}")
    for item in sorted(set(created)):
        print(f"  + {item}")
    for item in sorted(skipped):
        print(f"  = {item}（已存在，未覆盖）")
    return 0


def _cmd_pool_add(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    layout = config.layout
    owner, repo = parse_slug(args.slug)
    channel = args.channel or _infer_channel(config, f"{owner}/{repo}")
    clock: Clock = SystemClock()
    as_of = _optional_instant(args.as_of) or clock.now()

    snapshot = _snapshot_for(config, owner, repo, as_of=as_of, clock=clock)
    save_snapshot(layout, snapshot)
    # 显式 --as-of 时，观测时刻也取该值 → 入池可复现
    observe_clock: Clock = FixedClock(as_of) if args.as_of else clock
    observation = observe(layout, snapshot, channel=channel, clock=observe_clock)
    series = load_series(layout)
    count = next(
        (
            item.observed_days
            for item in series
            if item.repo == snapshot.slug and item.channel == channel
        ),
        1,
    )
    print(f"已入池：{snapshot.slug}  channel={channel}  观测数={count}")
    print(f"  快照：{snapshot.sha256[:16]}…  stars={observation.stars} forks={observation.forks}")
    if snapshot.degraded_sources:
        print(f"  ⚠ 降级来源：{', '.join(snapshot.degraded_sources)}（不影响退出码）")
    return 0


def _cmd_pool_list(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    as_of = _optional_instant(args.as_of) or SystemClock().now()
    series = load_series(config.layout)
    if not series:
        print("候选池为空。先运行 `python -m osslens pool add <owner/repo>`。")
        return 0

    payload: list[dict[str, Any]] = []
    for channel in CHANNELS:
        rows = score_channel(config, series, channel=channel, as_of=as_of)
        if not rows:
            continue
        payload.extend(
            {
                "channel": row.channel,
                "repo": row.repo,
                "score": row.score,
                "observations": row.observations,
                "metrics": row.metrics,
            }
            for row in rows
        )
        if args.json:
            continue
        print(f"\n通道 {channel}（{len(rows)} 个仓库；分数仅用于本通道内排序）")
        print(_table_header(rows[0].metrics))
        for row in rows:
            metrics = "  ".join(f"{key}={_num(row.metrics[key])}" for key in sorted(row.metrics))
            print(f"  {row.repo:<32} {row.score:>9.4f}  obs={row.observations:<3} {metrics}")

    if args.json:
        print(stable_json(payload))
    else:
        print("\n注：hot 与 classic 量纲不同，分数不可跨通道比较（设计方案 §6.1）。")
    return 0


def _cmd_pool_eligible(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    as_of = _optional_instant(args.as_of) or SystemClock().now()
    series = load_series(config.layout)
    rows = evaluate_eligibility(config, series, as_of=as_of)
    if args.json:
        print(
            stable_json(
                [
                    {
                        "channel": row.channel,
                        "repo": row.repo,
                        "eligible": row.eligible,
                        "reason": row.reason,
                        "score": row.score,
                    }
                    for row in rows
                ]
            )
        )
        return 0

    eligible = [row for row in rows if row.eligible]
    excluded = [row for row in rows if not row.eligible]
    print(f"深挖候选（as-of {fmt_iso(as_of)}）：{len(eligible)} 个")
    for row in eligible:
        print(f"  ✓ [{row.channel}] {row.repo}  — {row.reason}")
    if excluded:
        print(f"\n已排除：{len(excluded)} 个")
        for row in excluded:
            print(f"  ✗ [{row.channel}] {row.repo}  — {row.reason}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    layout = config.layout
    owner, repo = parse_slug(args.slug)
    slug = f"{owner}/{repo}"
    channel = args.channel or _infer_channel(config, slug)
    clock: Clock = SystemClock()
    as_of = _optional_instant(args.as_of)

    snapshot = _snapshot_for(config, owner, repo, as_of=as_of or clock.now(), clock=clock)
    if as_of is None:
        as_of = parse_iso(snapshot.fetched_at)

    card = build_featcard(snapshot, as_of=as_of, channel=channel)
    estimated_tokens = max(1, len(stable_json(card)) // 4)
    events = load_events(layout)
    decision = resolve_depth(
        config,
        requested=args.depth,
        channel=channel,
        as_of=as_of,
        events=events,
        llm_available=LLM_AVAILABLE,
        estimated_prompt_tokens=estimated_tokens,
    )

    commit = str(card["identity"].get("commit") or "unknown")
    card_path = layout.featcard_path(owner, repo, commit)
    report_path = layout.report_path(owner, repo, fmt_date(as_of))

    if args.dry_run:
        print(f"[dry-run] {slug}  通道={channel}  请求档位={decision.requested}")
        print(f"[dry-run] 实际档位={decision.actual}  原因={decision.reason}")
        for step in decision.chain:
            print(f"  - {step}")
        print(f"[dry-run] 将写：{_rel(card_path, layout.root)} / {_rel(report_path, layout.root)}")
        if decision.downgraded:
            print("[dry-run] 将追加 costs.jsonl：event=downgrade")
        return 0

    save_snapshot(layout, snapshot)
    atomic_write_text(card_path, stable_json(card) + "\n")

    report = render_report(
        ReportInputs(
            owner=owner,
            repo=repo,
            as_of=as_of,
            channel=channel,
            domain=str(args.domain),
            requested_depth=decision.requested,
            decision=decision,
            card=card,
            snapshot_sha256=snapshot.sha256,
            snapshot_notes=snapshot.notes,
            featcard_relpath=_rel(card_path, layout.root),
        )
    )
    atomic_write_text(report_path, report)

    ledger_written = False
    if decision.downgraded:
        ledger_written = record_event(
            layout, build_ledger_event(repo=slug, as_of=as_of, decision=decision)
        )

    print(f"报告：{_rel(report_path, layout.root)}")
    print(f"特征卡：{_rel(card_path, layout.root)}")
    print(f"档位：请求 {decision.requested} → 实际 {decision.actual}（{decision.reason}）")
    print(f"配额：{decision.quota.summary()}")
    if decision.downgraded:
        suffix = "" if ledger_written else "（同事件已存在，未重复追加）"
        print(f"留痕：costs.jsonl event=downgrade{suffix}")
    if snapshot.degraded_sources:
        print(f"⚠ 降级来源：{', '.join(snapshot.degraded_sources)}（退出码仍为 0）")
    return 0


def _cmd_cost(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    as_of = _optional_instant(args.as_of) or SystemClock().now()
    summary = summarize(config, load_events(config.layout), as_of=as_of)
    if args.json:
        print(
            stable_json(
                {
                    "as_of": summary.as_of,
                    "budget_month_remaining": summary.budget_month_remaining,
                    "budget_week_remaining": summary.budget_week_remaining,
                    "by_depth": summary.by_depth,
                    "cost_complete": summary.cost_complete,
                    "month_blocked": summary.month_blocked,
                    "month_cost": summary.month_cost,
                    "month_downgrades": summary.month_downgrades,
                    "month_start": summary.month_start,
                    "month_tokens": summary.month_tokens,
                    "week_blocked": summary.week_blocked,
                    "week_cost": summary.week_cost,
                    "week_downgrades": summary.week_downgrades,
                    "week_start": summary.week_start,
                    "week_tokens": summary.week_tokens,
                }
            )
        )
        return 0

    print(f"成本台账（as-of {summary.as_of}）")
    print(
        f"  本周（起 {summary.week_start}）：tokens {summary.week_tokens:,}，"
        f"费用 {_money(summary.week_cost, summary.cost_complete)}，"
        f"降级 {summary.week_downgrades} 次，预算拦截 {summary.week_blocked} 次"
    )
    print(
        f"  本月（起 {summary.month_start}）：tokens {summary.month_tokens:,}，"
        f"费用 {_money(summary.month_cost, summary.cost_complete)}，"
        f"降级 {summary.month_downgrades} 次，预算拦截 {summary.month_blocked} 次"
    )
    print(f"  本周按档位调用分布：{summary.by_depth or '—'}")
    week_left = f"{summary.budget_week_remaining:,}"
    month_left = f"{summary.budget_month_remaining:,}"
    print(f"  预算剩余：周 {week_left} tok / 月 {month_left} tok")
    if not summary.cost_complete:
        print("  费用：—（单价表未配置或存在未计价调用；单价由项目负责人填 config.yaml）")
    return 0


# --------------------------------------------------------------------------- 辅助


def _snapshot_for(
    config: Config, owner: str, repo: str, *, as_of: datetime, clock: Clock
) -> RepoSnapshot:
    cached = load_snapshot(config.layout, owner, repo, as_of)
    if cached is not None:
        return cached
    client = HttpClient(
        config.github_base_url,
        token=config.github_token(),
        user_agent=f"osslens/{__version__}",
    )
    try:
        return fetch_snapshot(client, owner, repo, as_of=as_of, clock=clock)
    finally:
        client.close()


def _infer_channel(config: Config, slug: str) -> str:
    if slug in config.watchlist:
        return WATCHLIST
    for item in load_series(config.layout):
        if item.repo == slug:
            return item.channel
    return CLASSIC


def _optional_instant(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_iso(value)
    except ValueError as exc:
        raise UsageError(f"--as-of 不是合法 ISO8601：{value!r}") from exc


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _table_header(metrics: dict[str, float]) -> str:
    columns = "  ".join(sorted(metrics))
    return f"  {'repo':<32} {'score':>9}  {'obs':<5} {columns}"


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _money(amount: float, complete: bool) -> str:
    if not complete and amount == 0:
        return "—"
    return f"{amount:.4f}"


__all__ = ["LLM_AVAILABLE", "main"]
