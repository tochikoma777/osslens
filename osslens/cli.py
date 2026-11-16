"""命令行入口：参数解析 / 子命令分发 / 退出码兜底。

退出码契约（写死）：0 完成（可能已降级/被拦）· 1 配置或真错误 · 2 参数错误。
可选源失败、配额耗尽、预算拦截、未配 key、超调用上限一律 **0**。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .abstract import (
    TYPE_CROSS_DOMAIN,
    CachedModelCaller,
    LlmModelCaller,
    cluster_run,
    cross_domain_run,
    load_runs,
    load_samples,
)
from .collect import (
    ExternalProbe,
    RepoSnapshot,
    fetch_snapshot,
    fetch_sources,
    load_snapshot,
    parse_slug,
    probe_external,
    save_snapshot,
)
from .config import CONFIG_TEMPLATE, Config, Layout
from .depth import (
    REQUESTED_DEPTHS,
    CostEvent,
    build_ledger_event,
    estimate_cost,
    load_events,
    record_event,
    resolve_depth,
    run_id_for,
    summarize,
)
from .featcard import build_featcard
from .llm import (
    MAX_CONTEXT_FILE_CHARS,
    MAX_CONTEXT_FILES,
    LlmClient,
    LlmOutcome,
    assemble_context,
    cache_key,
    cache_path,
    load_cached,
    store_cache,
    validate_insight,
)
from .pool import (
    CHANNELS,
    CLASSIC,
    WATCHLIST,
    evaluate_eligibility,
    load_series,
    observe,
    score_channel,
    threshold_flags,
)
from .prompts import FAST_INSIGHT_SYSTEM, STRONG_INSIGHT_SYSTEM, fast_insight_user
from .render import CostLine, ReportInputs, detect_cost_anomalies, render_report
from .retention import apply_retention, archive_snapshots
from .site import (
    build_site,
    resolve_site_as_of,
    site_check,
    write_site,
)
from .util import (
    Clock,
    ConfigError,
    FixedClock,
    HttpClient,
    OsslensError,
    SystemClock,
    UsageError,
    as_str,
    atomic_write_text,
    fmt_date,
    fmt_iso,
    parse_iso,
    stable_json,
)

# L2：fast 与 strong 两档均已接入（strong = deepseek-v4-pro + thinking）
AVAILABLE_DEPTHS = frozenset({"fast", "strong"})
PURPOSE_BY_DEPTH = {"fast": "fast_insight", "strong": "strong_insight"}
INSIGHT_PURPOSES = frozenset(PURPOSE_BY_DEPTH.values())
PURPOSE_INSIGHT = "fast_insight"  # 兼容旧引用；新代码一律走 PURPOSE_BY_DEPTH

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
        description="低成本、可长期运行的开源项目深度分析系统（L4：静态只读站点）",
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
    analyze_parser.add_argument(
        # 内部触发：自动链默认档位（depth.auto_default）走全链闸门，而非人工 override。
        # help 隐藏以保持 --help 已文档化的 CLI 表面不变（V9）。
        "--auto-chain",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    analyze_parser.add_argument("--channel", choices=CHANNELS, default=None)
    analyze_parser.add_argument("--domain", default="未指定")
    analyze_parser.add_argument("--as-of", dest="as_of", default=None)
    analyze_parser.add_argument("--dry-run", action="store_true", help="只打印决策，不落盘")
    analyze_parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="跳过非降级台账；降级事件永不跳过（红线 #10）",
    )
    analyze_parser.add_argument(
        "--no-sources", action="store_true", help="不下载源码切片（证据/依赖图将为空）"
    )
    analyze_parser.set_defaults(handler=_cmd_analyze)

    cost_parser = sub.add_parser("cost", parents=[common], help="成本台账")
    cost_parser.add_argument("--as-of", dest="as_of", default=None)
    cost_parser.add_argument("--json", action="store_true")
    cost_parser.set_defaults(handler=_cmd_cost)

    abstract_parser = sub.add_parser(
        "abstract", parents=[common], help="L3 规律抽象（批量触发 / 零 LLM 召回）"
    )
    abstract_parser.add_argument("--as-of", dest="as_of", default=None)
    abstract_parser.add_argument("--cluster", default=None, help="指定 domain.id 簇")
    abstract_parser.add_argument("--off", action="store_true", help="强制零 LLM")
    abstract_parser.add_argument(
        "--cross",
        action="store_true",
        help="跨域抽象 run（独立入口，不与簇内 run 混排；消费 L2 条目数 / 簇内 run 数阈值）",
    )
    abstract_parser.add_argument("--dry-run", action="store_true", help="只打印决策，不落盘")
    abstract_parser.add_argument("--json", action="store_true")
    abstract_parser.set_defaults(handler=_cmd_abstract)

    site_parser = sub.add_parser(
        "site", parents=[common], help="L4 静态只读站点（零 LLM / 零网络 / ¥0）"
    )
    site_parser.add_argument("--out", default=None, help="产物目录（默认 <root>/site）")
    site_parser.add_argument("--as-of", dest="as_of", default=None)
    site_parser.add_argument(
        "--check", action="store_true", help="只比对不写盘，给出差异清单，退出码默认恒 0"
    )
    site_parser.add_argument(
        "--strict",
        action="store_true",
        help="仅配合 --check：有差异时退出码 1（CI 用；本地缺省保持 0）",
    )
    site_parser.set_defaults(handler=_cmd_site)

    retention_parser = sub.add_parser(
        "retention", parents=[common], help="缓存层保留策略（默认 dry-run，--apply 才实际清理）"
    )
    retention_parser.add_argument("--as-of", dest="as_of", default=None)
    retention_parser.add_argument(
        "--apply",
        action="store_true",
        help="实际归档缓存层文件；缺省只规划不写盘（dry_run=True）",
    )
    retention_parser.add_argument(
        "--snapshots-only",
        action="store_true",
        help="只处理超保留期的快照元数据（原地 gzip），不动 src/ 与 llm_cache/；供定时建池使用",
    )
    retention_parser.add_argument("--json", action="store_true")
    retention_parser.set_defaults(handler=_cmd_retention)

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

    if layout.library_patterns.exists():
        skipped.append("patterns/library.yaml")
    else:
        # L3 / S4：真源初始为空，绝不用合成条目充数。
        atomic_write_text(layout.library_patterns, "[]\n")
        created.append("patterns/library.yaml")

    for path in (
        "data/ledger/",
        "data/pool/",
        "data/snapshots/",
        "data/featcards/",
        "data/costs/",
        "data/llm_cache/",
        "data/abstract/",
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
    slug = f"{owner}/{repo}"
    channel = args.channel or _infer_channel(config, slug)
    clock: Clock = SystemClock()
    as_of = _optional_instant(args.as_of) or clock.now()

    snapshot = _snapshot_for(config, owner, repo, as_of=as_of, clock=clock)
    save_snapshot(layout, snapshot)
    observe_clock: Clock = FixedClock(as_of) if args.as_of else clock
    repo_meta = snapshot.data.get("repo", {})
    flags = threshold_flags(
        config,
        load_series(layout),
        repo=slug,
        channel=channel,
        stars=int(repo_meta.get("stars") or 0),
        created_at=as_str(repo_meta.get("created_at")),
        observed_at=observe_clock.now(),
    )
    observation = observe(layout, snapshot, channel=channel, clock=observe_clock, flags=flags)
    series = load_series(layout)
    count = next(
        (item.observed_days for item in series if item.repo == slug and item.channel == channel),
        1,
    )
    print(f"已入池：{slug}  channel={channel}  观测数={count}")
    print(f"  快照：{snapshot.sha256[:16]}…  stars={observation.stars} forks={observation.forks}")
    if flags:
        print(f"  ⚠ 未达通道门槛（仍入池，D6-6）：{'；'.join(flags)}")
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
        flags = {item.repo: item.latest.flags for item in series if item.channel == channel}
        payload.extend(
            {
                "channel": row.channel,
                "repo": row.repo,
                "score": row.score,
                "observations": row.observations,
                "metrics": row.metrics,
                "threshold_flags": list(flags.get(row.repo, ())),
            }
            for row in rows
        )
        if args.json:
            continue
        print(f"\n通道 {channel}（{len(rows)} 个仓库；分数仅用于本通道内排序）")
        print(_table_header(rows[0].metrics))
        for row in rows:
            metrics = "  ".join(f"{key}={_num(row.metrics[key])}" for key in sorted(row.metrics))
            mark = "  ⚠ 未达门槛" if flags.get(row.repo) else ""
            print(f"  {row.repo:<32} {row.score:>9.4f}  obs={row.observations:<3}{mark}  {metrics}")
            for flag in flags.get(row.repo, ()):
                print(f"    - {flag}")

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

    sources, source_note = _sources_for(config, layout, snapshot, as_of=as_of, skip=args.no_sources)
    card = build_featcard(snapshot, as_of=as_of, channel=channel, config=config, sources=sources)
    commit = as_str(card["identity"].get("commit")) or "unknown"
    card_path = layout.featcard_path(owner, repo, commit)
    report_path = layout.report_path(owner, repo, fmt_date(as_of))

    tree_paths = [
        as_str(item.get("path"))
        for item in card.get("sources", {}).get("files", [])
        if isinstance(item, dict)
    ]

    external: ExternalProbe | None = None
    if not args.dry_run:
        external = probe_external(
            config,
            layout,
            owner,
            repo,
            as_of=as_of,
            clock=clock,
            repo_paths=tree_paths or _tree_paths(snapshot),
        )

    context = _build_context(config, card, sources)
    estimated = context.tokens if context else 0
    events = _events_excluding_current(load_events(layout), repo=slug, as_of=as_of)
    # auto_chain=True（隐藏的 --auto-chain）：自动链同一 --depth fast 走全链闸门，
    # 不进入 resolve_depth 的 L4 人工 override（手动 --depth 四档不受影响：默认 False）。
    decision = resolve_depth(
        config,
        requested=args.depth,
        channel=channel,
        as_of=as_of,
        events=events,
        available_depths=AVAILABLE_DEPTHS,
        estimated_prompt_tokens=estimated,
        auto_chain=bool(args.auto_chain),
    )

    if args.dry_run:
        print(f"[dry-run] {slug}  通道={channel}  请求档位={decision.requested}")
        print(f"[dry-run] 实际档位={decision.actual}  原因={decision.reason}")
        for step in decision.chain:
            print(f"  - {step}")
        print(
            f"[dry-run] 上下文估算 {estimated:,} tok（块 {len(context.blocks) if context else 0}）"
        )
        print(f"[dry-run] 将写：{_rel(card_path, layout.root)} / {_rel(report_path, layout.root)}")
        if decision.downgraded:
            print("[dry-run] 将追加 costs.jsonl：event=downgrade")
        return 0

    save_snapshot(layout, snapshot)
    atomic_write_text(card_path, stable_json(card) + "\n")

    outcome: LlmOutcome | None = None
    insight_reason = ""
    if decision.actual in AVAILABLE_DEPTHS:
        outcome, insight_reason = _run_insight(
            config,
            layout,
            repo=slug,
            card=card,
            sources=sources,
            context_text=context.text,
            allowed_paths=set(tree_paths),
            as_of=as_of,
            events=events,
            depth=decision.actual,
        )
    elif decision.actual != "off":
        insight_reason = f"{decision.actual} 档尚未接入，未发起调用"

    cost_line = _cost_line(
        config,
        layout,
        repo=slug,
        as_of=as_of,
        outcome=outcome,
        requested=decision.requested,
        actual=decision.actual,
    )
    _emit_actions_cost_warning(cost_line.anomalies)

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
            external=external,
            insight=outcome.insight if outcome and outcome.status in ("ok", "cache_hit") else None,
            insight_reason=insight_reason,
            context=context if decision.actual in AVAILABLE_DEPTHS else None,
            cost=cost_line,
        )
    )
    atomic_write_text(report_path, report)

    if decision.downgraded:
        ledger_event = build_ledger_event(repo=slug, as_of=as_of, decision=decision)
        written = record_event(layout, ledger_event)
        suffix = "" if written else "（同事件已存在，未重复追加）"
        print(f"留痕：costs.jsonl event={ledger_event.event}{suffix}")

    print(f"报告：{_rel(report_path, layout.root)}")
    print(f"特征卡：{_rel(card_path, layout.root)}")
    print(f"档位：请求 {decision.requested} → 实际 {decision.actual}（{decision.reason}）")
    print(f"配额：{decision.quota.summary()}")
    if source_note:
        print(f"⚠ 源码：{source_note}（证据/依赖图将为空，退出码仍为 0）")
    if external is not None:
        print(f"外部资料：{external.status} — {external.reason}")
    if outcome is not None:
        print(
            f"LLM：{outcome.status} via {outcome.format_used or '—'}  "
            f"in={outcome.usage.prompt_tokens} hit={outcome.usage.cache_hit_tokens} "
            f"out={outcome.usage.completion_tokens}"
        )
    if insight_reason:
        print(f"洞见：{insight_reason}")
    if cost_line.anomalies:
        print(f"成本异常（仅标注）：{'；'.join(cost_line.anomalies)}")
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
                    "anomalies": list(summary.anomalies),
                    "budget_month_remaining": summary.budget_month_remaining,
                    "budget_week_remaining": summary.budget_week_remaining,
                    "by_depth": summary.by_depth,
                    "by_purpose": summary.by_purpose,
                    "cost_complete": summary.cost_complete,
                    "month_blocked": summary.month_blocked,
                    "month_cache_hit_tokens": summary.month_cache_hit_tokens,
                    "month_cost": summary.month_cost,
                    "month_downgrades": summary.month_downgrades,
                    "month_start": summary.month_start,
                    "month_tokens": summary.month_tokens,
                    "week_blocked": summary.week_blocked,
                    "week_cache_hit_tokens": summary.week_cache_hit_tokens,
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
        f"  本周（起 {summary.week_start}）：tokens {summary.week_tokens:,}"
        f"（缓存命中 {summary.week_cache_hit_tokens:,}），"
        f"费用 {_money(summary.week_cost, summary.cost_complete)}，"
        f"降级 {summary.week_downgrades} 次，预算拦截 {summary.week_blocked} 次"
    )
    print(
        f"  本月（起 {summary.month_start}）：tokens {summary.month_tokens:,}"
        f"（缓存命中 {summary.month_cache_hit_tokens:,}），"
        f"费用 {_money(summary.month_cost, summary.cost_complete)}，"
        f"降级 {summary.month_downgrades} 次，预算拦截 {summary.month_blocked} 次"
    )
    if summary.by_depth:
        detail = "、".join(f"{key}={value}" for key, value in summary.by_depth.items())
        print(f"  本周按档位调用分布：{detail}")
    else:
        print("  本周按档位调用分布：—")
    if summary.by_purpose:
        for purpose, bucket in summary.by_purpose.items():
            print(
                f"  按用途 {purpose}：{bucket.get('calls', 0)} 次，{bucket.get('tokens', 0):,} tok"
            )
    else:
        print("  按用途分项：—")
    week_left = f"{summary.budget_week_remaining:,}"
    month_left = f"{summary.budget_month_remaining:,}"
    print(f"  预算剩余：周 {week_left} tok / 月 {month_left} tok")
    if summary.anomalies:
        print(f"  成本异常（仅标注，不阻断）：{'；'.join(summary.anomalies)}")
    if not summary.cost_complete:
        print("  费用：—（单价表未配置或存在未计价调用；单价由项目负责人填 config.yaml）")
    return 0


# --------------------------------------------------------------------------- L3 抽象


def _abstract_as_of(config: Config, raw: str | None) -> datetime:
    """时间只来自 `--as-of` 或输入样本；绝不取运行时钟（L3 卡红线 7）。"""
    explicit = _optional_instant(raw)
    if explicit is not None:
        return explicit
    samples, _ = load_samples(config.layout, config)
    stamps: list[datetime] = []
    for sample in samples:
        if not sample.analyzed_at:
            continue
        try:
            stamps.append(parse_iso(sample.analyzed_at))
        except ValueError:
            continue
    if stamps:
        return max(stamps)
    raise UsageError("工作区无真实样本且未传 --as-of：无法确定基准时间（时间不取运行时钟）")


def _cmd_abstract(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    as_of = _abstract_as_of(config, args.as_of)
    caller = None if args.off else CachedModelCaller(LlmModelCaller(config), config.layout)
    if args.cross:
        # 跨域 run：独立入口，不传 cluster；消费 L2 条目数 / 簇内 run 数阈值
        result = cross_domain_run(
            config,
            as_of=as_of,
            caller=caller,
            off=args.off,
            write=not args.dry_run,
        )
    else:
        result = cluster_run(
            config,
            as_of=as_of,
            cluster=args.cluster,
            caller=caller,
            off=args.off,
            write=not args.dry_run,
        )
    record = result.record
    if args.json:
        print(stable_json(record.to_json()))
        return 0

    samples, uncovered = load_samples(config.layout, config)
    counts: dict[str, int] = {}
    for sample in samples:
        if sample.domain is not None:
            counts[sample.domain] = counts.get(sample.domain, 0) + 1
    print(f"抽象 run：{record.run_id}  type={record.type}  cluster={record.cluster}")
    print(f"  基准时间 (as-of)：{record.created_at}  触发：{record.trigger}")
    print(
        f"  状态：{record.status}  LLM 调用={record.llm_calls}  ops={len(record.ops)}  "
        f"产出条目={len(record.produced_patterns)}"
    )
    print(f"  输入项目：{len(record.input_projects)} 个（增量 run 不全量重喂）")
    print(f"  规律库现有条目：{len(result.entries)}")
    print(f"  各簇真实样本：{counts or '—'}")
    if uncovered:
        print(f"  归类缺口（未自行补规则）：{', '.join(uncovered)}")
    check = record.self_check
    print("  自检四问：")
    print(f"    ① 可下钻到代码证据：{'是' if check.has_drilldown_evidence else '否'}")
    print(f"    ② 新增反例：{check.new_counterexamples} 条")
    print(f"    ③ 跨域证据：{'有' if check.has_cross_domain_evidence else '无'}")
    print(f"    ④ 抽检位：{check.manual_review_target}")
    for warning in record.warnings:
        print(f"  ⚠ {warning}")
    if record.status == "insufficient_samples":
        if record.type == TYPE_CROSS_DOMAIN:
            print(
                "  ★ 跨域抽象未触发，原因：无真实 L2 条目或跨域阈值未达 "
                f"（L2 ≥ {config.abstract.cross_domain_min_l2_entries} / 每 "
                f"{config.abstract.cross_domain_every_cluster_runs} 次簇内 run）"
                "（本轮产 0 条，真源纯净）"
            )
        else:
            print(
                f"  ★ 首次真实抽象未触发，原因：样本不足 S1 阈值 "
                f"{config.abstract.cluster_min_new_projects}（本轮产 0 条，真源纯净）"
            )
    if args.dry_run:
        print("  [dry-run] 未落盘（run 记录 / 规律库 / 台账均未写）")
    else:
        print(f"  run 记录：{_rel(config.layout.abstract_runs_jsonl, config.layout.root)}")
        print(f"  历史 run 数：{len(load_runs(config.layout))}")
    return 0


# --------------------------------------------------------------------------- L4 静态站点


def _cmd_site(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    as_of = resolve_site_as_of(config.layout, args.as_of)
    out_dir = Path(args.out).resolve() if args.out else config.layout.site_dir
    plan = build_site(config, as_of=as_of)

    if args.check:
        diffs = site_check(out_dir, plan.files)
        if diffs:
            print(f"site --check：发现 {len(diffs)} 处差异（未写盘）")
            for item in diffs:
                print(f"  - {item}")
        else:
            print(f"site --check：一致（{len(plan.files)} 个产物，as-of {plan.as_of}；未写盘）")
        # 缺省恒 0（只标注）；--strict 供 CI 把漂移变成红灯
        return 1 if (args.strict and diffs) else 0
    if args.strict:
        raise UsageError("--strict 只能与 --check 联用")

    statuses = write_site(out_dir, plan.files)
    print(f"静态站点：{out_dir}")
    print(
        f"  as-of {plan.as_of}  报告 {plan.report_count} · 特征卡 {plan.featcard_count} · "
        f"规律库 {plan.pattern_count} · run {plan.run_count}"
    )
    for status in statuses:
        print(f"  {status}")
    print(f"  索引（纯 MD）：{out_dir / 'index.md'}")
    print(f"  入口：{out_dir / 'index.html'}")
    print("  零 LLM / 零网络：本命令不构造任何 HTTP 客户端，不发起请求（增量成本 ¥0）")
    if plan.empty_note:
        print(f"  ⚠ {plan.empty_note}")
    return 0


# --------------------------------------------------------------------------- T5 缓存保留策略


def _cmd_retention(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.root))
    as_of = _optional_instant(args.as_of) or SystemClock().now()
    dry_run = not args.apply
    snapshots_done = archive_snapshots(config.layout, config, as_of, dry_run=dry_run)
    if args.snapshots_only:
        if args.json:
            print(
                stable_json(
                    {
                        "as_of": fmt_iso(as_of),
                        "dry_run": dry_run,
                        "snapshots_archived": list(snapshots_done),
                    }
                )
            )
            return 0
        mode = "dry-run（未写盘）" if dry_run else "apply（已归档）"
        print(f"快照保留策略：{mode}  基准时间 {fmt_iso(as_of)}")
        keep_days = config.retention.snapshot_keep_days
        print(f"  归档快照 {len(snapshots_done)} 个（超 {keep_days} 天原地 gzip）")
        for item in snapshots_done:
            print(f"    - {item}")
        return 0
    result = apply_retention(config.layout, config, as_of, dry_run=dry_run)
    if args.json:
        print(
            stable_json(
                {
                    "as_of": fmt_iso(as_of),
                    "dry_run": result.dry_run,
                    "cache_files": list(result.cache_files),
                    "unique_objects": list(result.unique_objects),
                    "duplicate_files": list(result.duplicate_files),
                    "archived": list(result.archived),
                    "snapshots_archived": list(snapshots_done),
                    "protected": list(result.protected),
                    "bytes_reclaimable": result.bytes_reclaimable,
                }
            )
        )
        return 0
    mode = "dry-run（未写盘）" if result.dry_run else "apply（已归档）"
    print(f"缓存保留策略：{mode}  基准时间 {fmt_iso(as_of)}")
    print(
        f"  缓存文件 {len(result.cache_files)} · 唯一对象 {len(result.unique_objects)} · "
        f"重复 {len(result.duplicate_files)}"
    )
    print(f"  归档缓存 {len(result.archived)} 个 · 可回收 {result.bytes_reclaimable} B")
    keep_days = config.retention.snapshot_keep_days
    print(f"  归档快照 {len(snapshots_done)} 个（超 {keep_days} 天原地 gzip）")
    print(f"  受保护真源 / 派生基线 {len(result.protected)} 个")
    for item in result.archived:
        print(f"    - {item}")
    if result.dry_run:
        print("  ★ 默认 dry-run，不写盘；显式 --apply 才实际移动缓存层文件")
    else:
        print(
            "  ★ 仅归档 src/ 与 llm_cache/；external/ · 三个 jsonl · "
            "patterns/ · reports/ · costs/ · site/ 均未触碰"
        )
    return 0


# --------------------------------------------------------------------------- LLM


def _run_insight(
    config: Config,
    layout: Layout,
    *,
    repo: str,
    card: dict[str, Any],
    sources: Any,
    context_text: str,
    allowed_paths: set[str],
    as_of: datetime,
    events: Sequence[CostEvent],
    depth: str,
) -> tuple[LlmOutcome | None, str]:
    credentials = config.llm_credentials()
    if credentials is None:
        return None, "未配置凭据（本应已降级）"

    model = config.model_for(depth)
    thinking = config.llm.thinking.get(depth, False)
    max_tokens = config.max_output_for(depth)
    purpose = PURPOSE_BY_DEPTH.get(depth, PURPOSE_INSIGHT)
    system = STRONG_INSIGHT_SYSTEM if depth == "strong" else FAST_INSIGHT_SYSTEM
    file_list = "\n".join(f"- {path}" for path in sorted(allowed_paths)) or "- （无）"
    files_block = context_text
    user = fast_insight_user(
        repo=repo,
        commit=as_str(card["identity"].get("commit")),
        featcard_json=stable_json(card),
        file_list=file_list,
        files_block=files_block,
    )
    key = cache_key(model, thinking, system, user)
    cached = load_cached(cache_path(layout, key))
    if cached is not None:
        _record_cache_hit(config, layout, repo, as_of, cached.model or model, depth, purpose)
        if cached.insight is not None:
            cached = LlmOutcome(
                status=cached.status,
                reason=cached.reason,
                insight=validate_insight(cached.insight, allowed_paths=allowed_paths),
                usage=cached.usage,
                model=cached.model,
                format_used=cached.format_used,
                calls=0,
            )
        return cached, ""

    if config.depth.budget.max_calls_per_run < 1:
        _record_blocked(config, layout, repo, as_of, model, "max_calls_per_run", depth, purpose)
        return None, f"超出单次调用上限 max_calls_per_run={config.depth.budget.max_calls_per_run}"

    client = LlmClient(
        credentials,
        model=model,
        thinking=thinking,
        timeout_seconds=config.llm.timeout_seconds,
        max_retries=config.llm.max_retries,
    )
    outcome = client.chat_json(system, user, max_tokens=max_tokens)
    if outcome.status != "ok" or outcome.insight is None:
        if outcome.usage.total_tokens:
            _record_call(
                config,
                layout,
                repo,
                as_of,
                model,
                outcome,
                cost=None,
                depth=depth,
                purpose=purpose,
            )
        return outcome, outcome.reason or "调用失败"

    insight = validate_insight(outcome.insight, allowed_paths=allowed_paths)
    outcome = LlmOutcome(
        status="ok",
        reason="",
        insight=insight,
        usage=outcome.usage,
        model=outcome.model,
        format_used=outcome.format_used,
        calls=outcome.calls,
    )
    store_cache(cache_path(layout, key), outcome)
    _record_call(
        config,
        layout,
        repo,
        as_of,
        model,
        outcome,
        cost=None,
        depth=depth,
        purpose=purpose,
    )
    if not insight.items:
        return outcome, f"全部条目被代码丢弃（{len(insight.dropped)} 条）：无有效证据"
    return outcome, ""


def _record_call(
    config: Config,
    layout: Layout,
    repo: str,
    as_of: datetime,
    model: str,
    outcome: LlmOutcome,
    *,
    cost: float | None,
    depth: str,
    purpose: str,
) -> None:
    as_of_iso = fmt_iso(as_of)
    usage = outcome.usage
    if cost is None:
        # 输出单价已覆盖 reasoning_tokens（它含在 completion_tokens 内），不重复计费
        cost = estimate_cost(
            config,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cache_hit_tokens=usage.cache_hit_tokens,
        )
    event = CostEvent(
        event="call",
        repo=repo,
        depth=depth,
        model=model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        estimated_cost=cost,
        source="api",
        as_of=as_of_iso,
        run_id=run_id_for(repo, as_of_iso, depth, depth, purpose),
        requested_depth=depth,
        actual_depth=depth,
        reason="",
        cache_hit_tokens=usage.cache_hit_tokens,
        cache_miss_tokens=usage.cache_miss_tokens,
        purpose=purpose,
        reasoning_tokens=usage.reasoning_tokens,
    )
    record_event(layout, event)


def _record_cache_hit(
    config: Config,
    layout: Layout,
    repo: str,
    as_of: datetime,
    model: str,
    depth: str,
    purpose: str,
) -> None:
    """缓存命中不花钱，但必须在台账里看得见（M6）。"""
    as_of_iso = fmt_iso(as_of)
    record_event(
        layout,
        CostEvent(
            event="cache_hit",
            repo=repo,
            depth=depth,
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost=0.0,
            source="cache",
            as_of=as_of_iso,
            run_id=run_id_for(repo, as_of_iso, depth, depth, "cache_hit"),
            requested_depth=depth,
            actual_depth=depth,
            reason="result_cache",
            purpose=purpose,
        ),
    )


def _record_blocked(
    config: Config,
    layout: Layout,
    repo: str,
    as_of: datetime,
    model: str,
    reason: str,
    depth: str,
    purpose: str,
) -> None:
    as_of_iso = fmt_iso(as_of)
    record_event(
        layout,
        CostEvent(
            event="blocked",
            repo=repo,
            depth="off",
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost=None,
            source="skipped",
            as_of=as_of_iso,
            run_id=run_id_for(repo, as_of_iso, depth, "off", reason),
            requested_depth=depth,
            actual_depth="off",
            reason=reason,
            purpose=purpose,
        ),
    )


# --------------------------------------------------------------------------- 辅助


def _sources_for(
    config: Config,
    layout: Layout,
    snapshot: RepoSnapshot,
    *,
    as_of: datetime,
    skip: bool,
) -> tuple[Any, str]:
    if skip:
        return None, "已按 --no-sources 跳过源码采集"
    commit = as_str(snapshot.data.get("repo", {}).get("default_branch")) and ""
    del commit
    commits = snapshot.data.get("commits")
    sha = ""
    if isinstance(commits, list) and commits:
        first = commits[0]
        if isinstance(first, dict):
            sha = as_str(first.get("sha"))
    if not sha:
        return None, "快照无 commit，无法定位源码"
    try:
        return (
            fetch_sources(config, layout, snapshot.owner, snapshot.repo, commit=sha, as_of=as_of),
            "",
        )
    except OsslensError as exc:
        return None, f"源码采集失败（{exc}）"


def _build_context(config: Config, card: dict[str, Any], sources: Any) -> Any:
    """源码缺失时退化为「仅特征卡」上下文——fast 仍可基于确定性事实产出洞见。"""
    texts = sources.texts() if sources is not None else []
    readme = ""
    others: list[tuple[str, str]] = []
    degree: dict[str, int] = {}
    graph = card.get("deps", {}).get("graph", {})
    if isinstance(graph, dict):
        for edge in graph.get("edges", []):
            if isinstance(edge, list) and len(edge) == 2:
                degree[str(edge[0])] = degree.get(str(edge[0]), 0) + 1
                degree[str(edge[1])] = degree.get(str(edge[1]), 0) + 1
    for item, text in texts:
        if Path(item.path).name.lower().startswith("readme"):
            readme = text
            continue
        others.append((item.path, text))
    others.sort(key=lambda pair: (-degree.get(pair[0], 0), pair[0]))
    trimmed = [(path, text[:MAX_CONTEXT_FILE_CHARS]) for path, text in others[:MAX_CONTEXT_FILES]]
    others = trimmed
    return assemble_context(
        card_json=stable_json(card),
        readme=readme,
        source_files=others,
        budget_tokens=config.depth.budget.per_run_prompt_tokens,
    )


COST_ANOMALY_WARNING_TITLE = "成本异常（仅标注，不阻断）"


def _emit_actions_cost_warning(anomalies: Sequence[str]) -> None:
    """GitHub Actions 原生告警（仅标注、不阻断）。

    ★ 只在 `GITHUB_ACTIONS=true` 时输出，避免污染本地 CLI / 报告输出。
    ★ title 与 pool.yml 的「工作区有未提交改动」脏守卫显式区分，避免误读为构建失败。
    ★ 不改退出码、不写 degraded、不加任何阻断语义。
    """
    if not anomalies or os.environ.get("GITHUB_ACTIONS") != "true":
        return
    for item in anomalies:
        print(f"::warning title={COST_ANOMALY_WARNING_TITLE}::{item}")


def _cost_line(
    config: Config,
    layout: Layout,
    *,
    repo: str,
    as_of: datetime,
    outcome: LlmOutcome | None,
    requested: str,
    actual: str,
) -> CostLine:
    model = config.model_for(actual) if actual != "off" else config.model_for("fast")
    usage_tokens = outcome.usage if outcome is not None else None
    run_tokens = usage_tokens.total_tokens if usage_tokens else 0
    run_cost = (
        estimate_cost(
            config,
            model=model,
            prompt_tokens=usage_tokens.prompt_tokens,
            completion_tokens=usage_tokens.completion_tokens,
            cache_hit_tokens=usage_tokens.cache_hit_tokens,
        )
        if usage_tokens
        else None
    )

    events = _events_excluding_current(load_events(layout), repo=repo, as_of=as_of)
    summary = summarize(config, events, as_of=as_of)
    week_tokens = summary.week_tokens + run_tokens
    month_tokens = summary.month_tokens + run_tokens
    week_cost = summary.week_cost + (run_cost or 0.0)
    month_cost = summary.month_cost + (run_cost or 0.0)

    history = [
        event.prompt_tokens + event.completion_tokens
        for event in events
        if event.event == "call" and event.repo == repo
    ]
    anomalies = detect_cost_anomalies(
        week_tokens=week_tokens,
        month_tokens=month_tokens,
        run_tokens=run_tokens,
        weekly_tokens=config.depth.budget.weekly_tokens,
        monthly_tokens=config.depth.budget.monthly_tokens,
        history=history,
    )

    entry = config.llm.price_table.get(model)
    price_note = ""
    if entry is not None:
        price_note = (
            f"{model} 输入未命中 ¥{entry.prompt_per_1m:g}/M · 缓存命中 "
            f"¥{entry.cache_hit_per_1m:g}/M · 输出 ¥{entry.completion_per_1m:g}/M"
            "（官方中文页，核对 2026-11-03，取高峰价；低谷约为一半）"
        )
    # 报告描述「本次分析的成本」，与本次进程是否命中缓存无关 → 同 as-of 重跑字节一致
    has_usage = usage_tokens is not None and usage_tokens.total_tokens > 0
    return CostLine(
        run_cost=run_cost,
        calls=1 if has_usage else 0,
        prompt_tokens=usage_tokens.prompt_tokens if usage_tokens else 0,
        cache_hit_tokens=usage_tokens.cache_hit_tokens if usage_tokens else 0,
        completion_tokens=usage_tokens.completion_tokens if usage_tokens else 0,
        source="analysis" if has_usage else "skipped",
        week_cost=week_cost,
        week_tokens=week_tokens,
        month_cost=month_cost,
        month_tokens=month_tokens,
        model_prices=(price_note,) if price_note else (),
        anomalies=anomalies,
    )


def _events_excluding_current(
    events: Sequence[CostEvent], *, repo: str, as_of: datetime
) -> list[CostEvent]:
    """报告里的配额/累计只算「本次分析之外」的事件——保证同 as-of 重跑字节一致。

    全局口径看 `cost` 命令（它读完整台账）。
    """
    as_of_iso = fmt_iso(as_of)
    return [
        event
        for event in events
        if not (
            event.event == "call"
            and event.repo == repo
            and event.as_of == as_of_iso
            and event.purpose in INSIGHT_PURPOSES
        )
    ]


def _tree_paths(snapshot: RepoSnapshot) -> list[str]:
    entries = snapshot.data.get("tree", {})
    raw = entries.get("entries") if isinstance(entries, dict) else None
    if not isinstance(raw, list):
        return []
    return [as_str(item.get("path")) for item in raw if isinstance(item, dict)]


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


__all__ = ["AVAILABLE_DEPTHS", "main"]
