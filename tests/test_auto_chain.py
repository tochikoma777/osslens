"""路径 B 批次 A：自动链默认档位 / 成本异常阈值 / 报告头部独立区块。

★ 只标注、不阻断：异常判定不改变档位、不写 degraded、退出码恒 0。
★ 幂等：稳态（无异常）报告字节完全不变；异常区块只在命中时出现，且不新增第六区块。
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from osslens import abstract
from osslens.cli import PURPOSE_BY_DEPTH, main
from osslens.config import Config, Layout
from osslens.depth import (
    AUTO_ABSTRACT_PURPOSES,
    AUTO_ANALYSIS_PURPOSES,
    AUTO_RUN_ID_ENV,
    ORCHESTRATION_FIELD,
    REQUESTED_DEPTHS,
    CostEvent,
    auto_interval_reached,
    last_auto_call_at,
    load_events,
    orchestration_run_from_env,
    record_event,
    resolve_depth,
)
from osslens.pool import EligibilityRow, first_auto_slug, observe
from osslens.render import (
    CostLine,
    cost_anomaly_block,
    detect_cost_anomalies,
)
from osslens.util import ConfigError, FixedClock

from .conftest import AS_OF, make_snapshot, read_jsonl_file, seed_workspace

REPORT_NAME = "deepseek-ai__DeepEP__2026-11-02.md"


@pytest.fixture(autouse=True)
def _no_orchestration_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认清空自动链归因 env，保证 record_event 走手动/本地零影响路径；
    需要注入的用例自行 setenv（test_orchestration_attributed_when_env_injected）。
    """
    monkeypatch.delenv(AUTO_RUN_ID_ENV, raising=False)


def _cost(anomalies: tuple[str, ...]) -> CostLine:
    return CostLine(
        run_cost=0.0,
        calls=1,
        prompt_tokens=1,
        cache_hit_tokens=0,
        completion_tokens=1,
        source="api",
        week_cost=0.0,
        week_tokens=1,
        month_cost=0.0,
        month_tokens=1,
        model_prices=(),
        anomalies=anomalies,
    )


# --------------------------------------------------------------------------- 阈值专门断言


def test_detect_cost_anomalies_thresholds() -> None:
    """周 > 50% / 月 > 80% / 本次 > 中位数 × 3：边界与命中文案逐条断言。"""
    # 周阈值：恰好 50% 不触发（用 > 不是 >=），超过即触发
    at_half = detect_cost_anomalies(
        week_tokens=1000,
        month_tokens=0,
        run_tokens=0,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(),
    )
    assert "本周用量 > 周额度 50%" not in at_half

    over_half = detect_cost_anomalies(
        week_tokens=1001,
        month_tokens=0,
        run_tokens=0,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(),
    )
    assert "本周用量 > 周额度 50%" in over_half

    # 月阈值：80% 边界
    over_month = detect_cost_anomalies(
        week_tokens=0,
        month_tokens=8001,
        run_tokens=0,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(),
    )
    assert "本月用量 > 月额度 80%" in over_month
    at_month = detect_cost_anomalies(
        week_tokens=0,
        month_tokens=8000,
        run_tokens=0,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(),
    )
    assert "本月用量 > 月额度 80%" not in at_month


def test_detect_cost_anomalies_median_x3_and_zero_guard() -> None:
    """中位数 × 3：命中/不命中；中位数为 0 时跳过（不拿 0 冒充）。"""
    # 历史 [10, 20, 30] 中位数 20，本次 61 > 60 命中
    hit = detect_cost_anomalies(
        week_tokens=0,
        month_tokens=0,
        run_tokens=61,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(30, 10, 20),
    )
    assert any("近期中位数 20 tok 的 3 倍" in item for item in hit)

    miss = detect_cost_anomalies(
        week_tokens=0,
        month_tokens=0,
        run_tokens=60,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(10, 20, 30),
    )
    assert not any("中位数" in item for item in miss)

    # 中位数为 0：跳过突增判定，不产生异常
    zero_median = detect_cost_anomalies(
        week_tokens=0,
        month_tokens=0,
        run_tokens=100,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(0, 0, 0),
    )
    assert zero_median == ()

    # 稳态：全部不触发
    steady = detect_cost_anomalies(
        week_tokens=100,
        month_tokens=100,
        run_tokens=10,
        weekly_tokens=2000,
        monthly_tokens=10000,
        history=(10, 10, 10),
    )
    assert steady == ()


# --------------------------------------------------------------------------- 报告头部独立区块


def test_cost_anomaly_block_is_header_and_not_table() -> None:
    """头部独立区块：不与成本表格混排；空/无异常时不渲染任何行。"""
    block = cost_anomaly_block(_cost(("本周用量 > 周额度 50%", "本月用量 > 月额度 80%")))
    text = "\n".join(block)
    assert "成本异常（仅标注，不阻断）" in text
    assert "> - 本周用量 > 周额度 50%" in text
    assert "> - 本月用量 > 月额度 80%" in text
    # 不与成本表格混排：不得出现表格行
    assert all(not line.startswith("|") for line in block)
    # 空异常 / 无 cost：不渲染（保证稳态报告字节不变）
    assert cost_anomaly_block(_cost(())) == []
    assert cost_anomaly_block(None) == []


def test_analyze_emits_header_anomaly_block_when_threshold_hit(tmp_path: Path) -> None:
    """整条渲染链：预置本周大额台账 → 周用量 > 50% → 报告头部出现独立区块。

    断言：退出码 0 · 区块在「## 运行元数据」之前 · 无「| 成本异常 |」表格行
    · 仍为五区块 · 不产生 downgrade 事件（异常不写 degraded，只标注不阻断）。
    """
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    record_event(
        config.layout,
        CostEvent(
            event="call",
            repo="deepseek-ai/DeepEP",
            depth="fast",
            model="deepseek-flash",
            prompt_tokens=1_500_000,  # 周额度 2,000,000 的 50% = 1,000,000
            completion_tokens=0,
            estimated_cost=0.0,
            source="api",
            as_of="2026-11-02T09:00:00Z",
            run_id="seed-anomaly",
            requested_depth="fast",
            actual_depth="fast",
            reason="baseline",
            purpose="seed",  # 与本次 off 档不同 as_of/purpose，不被 _events_excluding_current 排除
        ),
    )
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--as-of",
            "2026-11-02T00:00:00Z",
            "--depth",
            "off",
        ]
    )
    assert code == 0
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "成本异常（仅标注，不阻断）" in text
    assert "本周用量 > 周额度 50%" in text
    # 头部独立：在第一个「## 区块」之前
    assert text.index("成本异常（仅标注，不阻断）") < text.index("## 运行元数据")
    # 不与成本表格混排
    assert "| 成本异常 |" not in text
    # 五区块顺序/数量不变（不新增第六区块）
    assert sum(1 for line in text.splitlines() if line.startswith("## ")) == 5
    # 异常不写 degraded：不产生新的 downgrade/blocked 事件
    rows = read_jsonl_file(config.layout.costs_jsonl)
    assert not any(r["event"] in ("downgrade", "blocked") for r in rows)


def test_analyze_emits_actions_warning_only_on_anomaly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """G1：异常命中 + GITHUB_ACTIONS=true → ::warning；文案与 pool.yml 脏守卫显式区分。"""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    record_event(
        config.layout,
        CostEvent(
            event="call",
            repo="deepseek-ai/DeepEP",
            depth="fast",
            model="deepseek-flash",
            prompt_tokens=1_500_000,
            completion_tokens=0,
            estimated_cost=0.0,
            source="api",
            as_of="2026-11-02T09:00:00Z",
            run_id="seed-actions-warning",
            requested_depth="fast",
            actual_depth="fast",
            reason="baseline",
            purpose="seed",
        ),
    )
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--as-of",
            "2026-11-02T00:00:00Z",
            "--depth",
            "off",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "::warning title=成本异常（仅标注，不阻断）::" in out
    assert "本周用量 > 周额度 50%" in out
    assert "工作区有未提交改动" not in out  # 与 pool.yml 脏守卫区分
    rows = read_jsonl_file(config.layout.costs_jsonl)
    assert not any(r["event"] in ("downgrade", "blocked") for r in rows)


def test_steady_report_has_no_anomaly_block(tmp_path: Path) -> None:
    """稳态（阈值未触发）：报告不含异常区块，字节与既有渲染一致（幂等不受影响）。"""
    root = seed_workspace(tmp_path / "ws")
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "成本异常" not in text
    assert "> ⚠" not in text
    assert sum(1 for line in text.splitlines() if line.startswith("## ")) == 5


# ---------------------------------------------------------------------------
# 路径 B 批次 A：A1 选候选 / C1.4 编排归因 / C1.1·C1.2 触发 / A-1 语义区分
# ---------------------------------------------------------------------------


def _call_event() -> CostEvent:
    return CostEvent(
        event="call",
        repo="deepseek-ai/DeepEP",
        depth="fast",
        model="deepseek-flash",
        prompt_tokens=10,
        completion_tokens=5,
        estimated_cost=0.0,
        source="api",
        as_of="2026-11-02T00:00:00Z",
        run_id="fixed",
        requested_depth="fast",
        actual_depth="fast",
        reason="",
    )


# --- A1：从 pool eligible 排序里取首个候选，跳过已报告/已 blocked/已降级 -------


def test_first_auto_slug_picks_first_eligible(tmp_path: Path) -> None:
    """A1：取排序里首个 eligible；分数只排序、不升档。"""
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    rows = [
        EligibilityRow("o/skip", "hot", False, "观察期未满", 9.0),
        EligibilityRow("o/first", "classic", True, "ok", 3.0),
        EligibilityRow("o/second", "classic", True, "ok", 2.0),
    ]
    assert first_auto_slug(rows, layout=config.layout) == "o/first"


def test_first_auto_slug_skips_spent_and_reported(tmp_path: Path) -> None:
    """A1：已 blocked / 已降级双写留痕 / 已产出报告的 slug 本轮不再选。"""
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    record_event(
        config.layout,
        CostEvent(
            event="blocked",
            repo="o/blocked",
            depth="off",
            model="",
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost=None,
            source="skipped",
            as_of="2026-11-02T00:00:00Z",
            run_id="b",
            requested_depth="fast",
            actual_depth="off",
            reason="budget_blocked",
        ),
    )
    record_event(
        config.layout,
        CostEvent(
            event="downgrade",
            repo="o/downgraded",
            depth="off",
            model="",
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost=None,
            source="skipped",
            as_of="2026-11-02T00:00:00Z",
            run_id="d",
            requested_depth="fast",
            actual_depth="off",
            reason="no_credentials",
        ),
    )
    (root / "reports" / "o__reported__2026-11-02.md").write_text("# report\n", encoding="utf-8")
    rows = [
        EligibilityRow("o/blocked", "classic", True, "ok", 5.0),
        EligibilityRow("o/downgraded", "classic", True, "ok", 4.0),
        EligibilityRow("o/reported", "classic", True, "ok", 3.0),
        EligibilityRow("o/fresh", "classic", True, "ok", 1.0),
    ]
    assert first_auto_slug(rows, layout=config.layout) == "o/fresh"


def test_first_auto_slug_returns_none_when_no_candidate(tmp_path: Path) -> None:
    """A1：无合格候选 → None（调用方按 [skip] 退出码 0、不产生调用）。"""
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    assert first_auto_slug([], layout=config.layout) is None
    assert (
        first_auto_slug(
            [EligibilityRow("o/x", "hot", False, "观察期未满", 1.0)],
            layout=config.layout,
        )
        is None
    )


# --- C1.4：编排 run 归因（零侵入，手动/本地字节不变） -------------------------


def test_orchestration_run_from_env() -> None:
    assert orchestration_run_from_env({}) == ""
    assert orchestration_run_from_env({AUTO_RUN_ID_ENV: "42455959308"}) == "42455959308"


def test_orchestration_zero_impact_when_env_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1.4 / V8：未注入 env → costs.jsonl 行**结构完全不变**（整行 = 手动基线，多/少键均不允许）。"""
    monkeypatch.delenv(AUTO_RUN_ID_ENV, raising=False)
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    event = _call_event()
    expected = event.to_json()  # 手动 / 本地基线行（不含 orchestration_run）
    assert ORCHESTRATION_FIELD not in expected
    assert record_event(config.layout, event) is True
    rows = read_jsonl_file(config.layout.costs_jsonl)
    assert rows[0] == expected  # 整行逐键相等：结构不变，不只是「缺字段」
    assert set(rows[0]) == set(expected)


def test_orchestration_attributed_when_env_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1.4：注入 github.run_id → 编排 run 关联到每一笔 costs.jsonl 行，可读回。"""
    monkeypatch.setenv(AUTO_RUN_ID_ENV, "42455959308")
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    assert record_event(config.layout, _call_event()) is True
    rows = read_jsonl_file(config.layout.costs_jsonl)
    assert rows[0][ORCHESTRATION_FIELD] == "42455959308"
    loaded = load_events(config.layout)
    assert loaded[0].orchestration_run == "42455959308"


# --- C1.1/C1.2：独立 workflow 静态结构（不 push、不串编排器） ------------------


def _load_auto_workflow() -> tuple[str, dict]:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "auto.yml"
    raw = path.read_text(encoding="utf-8")
    return raw, yaml.safe_load(raw)


def test_auto_workflow_candidate_cron_and_independent_jobs() -> None:
    """S4'：候选 UTC 11:00 初值、无绝对时区断言、三段无 needs 依赖（不新增编排器）。"""
    raw, doc = _load_auto_workflow()
    triggers = doc.get("on", doc.get(True, {}))
    crons = [item["cron"] for item in triggers["schedule"]]
    assert crons == ["0 11 * * *"]
    assert "workflow_dispatch" in triggers
    assert "候选" in raw and "实测校准" in raw
    assert "每日" not in raw  # 不写死「每日 XX UTC」这类未核清的绝对时区断言
    jobs = doc["jobs"]
    assert set(jobs) == {"auto-analyze", "auto-abstract", "auto-site"}
    assert all("needs" not in job for job in jobs.values())
    runs = " ".join(str(job.get("runs-on", "")) for job in jobs.values())
    assert "ubuntu-24.04" in runs and "ubuntu-latest" not in runs


def test_auto_workflow_wiring_and_credential_safety() -> None:
    """A1/S1'/C1.4/A2 接线到位；两段并行回写；凭据只走 secrets、零打印。"""
    raw, _ = _load_auto_workflow()
    assert "first_auto_slug" in raw
    assert "config.depth.auto_default" in raw
    assert '"--auto-chain"' in raw  # 1.2：不把 fast 当人工 override
    assert "OSSLENS_AUTO_RUN_ID" in raw and "github.run_id" in raw
    assert "python -m osslens abstract" in raw
    assert "python -m osslens site --check" in raw
    assert "secrets.OSSLENS_LLM_API_KEY" in raw
    assert "secrets.OSSLENS_LLM_BASE_URL" in raw
    assert "echo $OSSLENS_LLM_API_KEY" not in raw  # 零打印凭据
    # 两段都回写：各自调用同一个并行安全脚本，两段都有写权限
    assert raw.count("bash scripts/auto_persist.sh") == 2
    assert raw.count("contents: write") == 2
    assert "git push" not in raw  # push 收敛到脚本，避免两段各写一套
    assert "git add -A" not in raw
    assert "git clean" not in raw

    repo = Path(__file__).resolve().parents[1]
    script = (repo / "scripts" / "auto_persist.sh").read_text(encoding="utf-8")
    assert "git push" in script
    assert "git rebase origin/main" in script
    assert "python -m osslens site" in script
    assert "git add --" in script
    assert "git add -A" not in script
    assert "git clean" not in script

    attrs = (repo / ".gitattributes").read_text(encoding="utf-8")
    for path in (
        "data/costs/costs.jsonl",
        "data/abstract/runs.jsonl",
        "data/pool/pool.jsonl",
        "patterns/ops.jsonl",
    ):
        assert f"{path} merge=union" in attrs


def test_purpose_sets_match_writers() -> None:
    """Z5：闸门用途集合必须与写入方字面量完全一致（改一边就失败，防静默失效）。"""
    assert frozenset(PURPOSE_BY_DEPTH.values()) == AUTO_ANALYSIS_PURPOSES
    assert (
        frozenset({abstract.TYPE_CLUSTER, abstract.TYPE_CROSS_DOMAIN, abstract.TYPE_RECONCILE})
        == AUTO_ABSTRACT_PURPOSES
    )


def test_abstract_anchor_survives_fresh_checkout(tmp_path: Path) -> None:
    """Z1/Z2：锚点落盘后，全新 Config / load_events 仍能读到 → schedule 未满即跳过。"""
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    event = replace(_attributed_call("2026-11-13T12:00:00Z"), purpose="cluster-abstraction")
    assert record_event(config.layout, event) is True

    # 模拟全新检出：重新加载配置与台账（不复用内存中的 events）
    fresh = Config.load(root)
    fresh_events = load_events(fresh.layout)
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)
    assert (
        auto_interval_reached(fresh, fresh_events, now=now, purposes=AUTO_ABSTRACT_PURPOSES)
        is False
    )
    # 分析段不被抽象段锚点影响
    assert (
        auto_interval_reached(fresh, fresh_events, now=now, purposes=AUTO_ANALYSIS_PURPOSES) is True
    )


def test_union_merge_keeps_both_append_only_sides(tmp_path: Path) -> None:
    """Z3：两段并行追加 costs.jsonl，union 合并后双方行都在（真实 git 实测，不 mock）。"""
    repo = tmp_path / "repo"
    (repo / "data" / "costs").mkdir(parents=True)

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    run("init", "-q", "-b", "main")
    run("config", "user.name", "t")
    run("config", "user.email", "t@t")

    (repo / ".gitattributes").write_text("data/costs/costs.jsonl merge=union\n", encoding="utf-8")
    costs = repo / "data" / "costs" / "costs.jsonl"
    costs.write_text('{"run":"base"}\n', encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "base")

    run("checkout", "-qb", "abstract")
    costs.write_text(
        '{"run":"base"}\n{"run":"abstract","orchestration_run":"1"}\n', encoding="utf-8"
    )
    run("add", "-A")
    run("commit", "-qm", "abstract")

    run("checkout", "-q", "main")
    costs.write_text(
        '{"run":"base"}\n{"run":"analyze","orchestration_run":"2"}\n', encoding="utf-8"
    )
    run("add", "-A")
    run("commit", "-qm", "analyze")
    run("merge", "--no-edit", "abstract")

    text = costs.read_text(encoding="utf-8")
    assert '"abstract"' in text
    assert '"analyze"' in text
    assert text.count('"run":"base"') == 1


# --- A-1：auto_default 只影响自动链，手动四档与 baseline 语义不变 --------------


def test_auto_default_separate_from_baseline(tmp_path: Path) -> None:
    """A-1：auto_default=fast 与 baseline 互不影响；requested=auto 仍由 baseline 推导。"""
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    assert config.depth.auto_default == "fast"
    assert config.depth.baseline == {"hot": "fast", "classic": "strong", "watchlist": "strong"}
    # 手动四档不变、默认 auto 不变
    assert REQUESTED_DEPTHS == ("auto", "off", "fast", "strong")
    # requested=auto 由通道基线 classic=strong 推导，与 auto_default=fast 无关
    decision = resolve_depth(
        config,
        requested="auto",
        channel="classic",
        as_of=datetime(2026, 11, 2, tzinfo=UTC),
        events=[],
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
    )
    assert decision.actual == "strong"  # baseline，而非 auto_default 的 fast


# ---------------------------------------------------------------------------
# 1.2 核心：自动链走全链成本闸门，绝不进入 resolve_depth 的 L4 人工 override
# ---------------------------------------------------------------------------


def _seed_fast_calls(layout: Layout, count: int = 3) -> None:
    """预置本周 N 条 fast call，用于耗尽 fast 周配额（3/周）。"""
    for index in range(count):
        record_event(
            layout,
            CostEvent(
                event="call",
                repo="seed/other",  # 与本次分析 repo 不同 → 不被 _events_excluding_current 排除
                depth="fast",
                model="deepseek-flash",
                prompt_tokens=1000,
                completion_tokens=0,
                estimated_cost=0.0,
                source="api",
                as_of="2026-11-02T09:00:00Z",
                run_id=f"seed-fast-{index}",
                requested_depth="fast",
                actual_depth="fast",
                reason="baseline",
                purpose="fast_insight",
            ),
        )


def test_auto_chain_never_enters_manual_override(tmp_path: Path) -> None:
    """V3：auto_chain 的 fast 走「L1 通道基线 → L2 周配额 → L3 预算/安全系数」，
    不停在 L4 人工 override；与手动 --depth fast 的差异由 auto_chain 标志决定而非值。"""
    config = Config.from_mapping(tmp_path)
    decision = resolve_depth(
        config,
        requested="fast",
        channel="classic",  # 通道基线 strong，自动链按 auto_default=fast 收敛
        as_of=datetime(2026, 11, 2, tzinfo=UTC),
        events=[],
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
        estimated_prompt_tokens=10,
        auto_chain=True,
    )
    assert decision.actual == "fast"
    assert decision.reason == "baseline"  # 不是 manual_override
    chain = " ".join(decision.chain)
    assert "L1 通道基线" in chain
    assert "L2 周配额" in chain
    assert "L3 预算" in chain
    assert "1.3" in chain  # estimate_safety_factor 生效
    assert "非 L4 人工 override" in chain
    # 对照：同值手动 --depth fast（auto_chain=False）才进人工 override
    manual = resolve_depth(
        config,
        requested="fast",
        channel="classic",
        as_of=datetime(2026, 11, 2, tzinfo=UTC),
        events=[],
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
        auto_chain=False,
    )
    assert manual.reason == "manual_override"


def test_auto_chain_fast_does_not_bypass_compute_quota(tmp_path: Path) -> None:
    """V5：fast 周配额 3/3 用满 → 自动链降级 off；手动 override 才绕过 compute_quota。"""
    config = Config.from_mapping(tmp_path)
    events = [
        CostEvent(
            event="call",
            repo="seed/other",
            depth="fast",
            model="deepseek-flash",
            prompt_tokens=1000,
            completion_tokens=0,
            estimated_cost=0.0,
            source="api",
            as_of="2026-11-02T09:00:00Z",
            run_id=f"q-{i}",
            requested_depth="fast",
            actual_depth="fast",
            reason="baseline",
            purpose="fast_insight",
        )
        for i in range(3)
    ]
    auto = resolve_depth(
        config,
        requested="fast",
        channel="classic",
        as_of=datetime(2026, 11, 2, tzinfo=UTC),
        events=events,
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
        auto_chain=True,
    )
    assert auto.actual == "off"
    assert auto.reason == "weekly_quota_exhausted"
    assert auto.downgraded is True
    # 对照：手动 --depth fast 绕过周配额（既有 L4 语义，未被本卡改变）
    manual = resolve_depth(
        config,
        requested="fast",
        channel="classic",
        as_of=datetime(2026, 11, 2, tzinfo=UTC),
        events=events,
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
        auto_chain=False,
    )
    assert manual.actual == "fast"
    assert manual.reason == "manual_override"


def test_auto_chain_weekly_quota_exhausted_downgrades_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V4：周配额耗尽时自动链端到端 —— 不调模型、降级双写、rc=0、候选留池。

    对齐 docs/成本预算.md「拦截后候选仍在池 / 不截断单次生成」与
    tests/test_l2.py 的预算拦截测试风格（报告降级字样 + costs.jsonl 留痕 + 候选不丢）。
    """
    monkeypatch.setenv("OSSLENS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OSSLENS_LLM_BASE_URL", "https://llm.invalid")
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    observe(config.layout, make_snapshot(), channel="hot", clock=FixedClock(AS_OF))
    _seed_fast_calls(config.layout, count=3)  # fast 3/3 用满

    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "fast",
            "--auto-chain",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0
    rows = read_jsonl_file(config.layout.costs_jsonl)
    # 不调用模型：call 事件仍只有预置的 3 条
    assert sum(1 for r in rows if r["event"] == "call") == 3
    # 降级双写留痕（L2 周配额耗尽 → downgrade 事件）
    assert any(r["event"] == "downgrade" and r["reason"] == "weekly_quota_exhausted" for r in rows)
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "本周配额已用满" in text  # 报告元数据降级字样
    # 候选不因拦截被丢弃
    assert read_jsonl_file(config.layout.pool_jsonl), "候选不得因拦截被丢弃"


def test_auto_chain_budget_blocked_writes_blocked_and_keeps_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V4：L3 预算拦截时自动链不调模型、写 blocked 事件、rc=0、候选留池。"""
    monkeypatch.setenv("OSSLENS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OSSLENS_LLM_BASE_URL", "https://llm.invalid")
    root = seed_workspace(
        tmp_path / "ws", overrides={"depth": {"budget": {"per_run_prompt_tokens": 1}}}
    )
    config = Config.load(root)
    observe(config.layout, make_snapshot(), channel="hot", clock=FixedClock(AS_OF))

    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "fast",
            "--auto-chain",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0
    rows = read_jsonl_file(config.layout.costs_jsonl)
    assert sum(1 for r in rows if r["event"] == "call") == 0  # 未调用模型
    assert any(r["event"] == "blocked" and r["reason"] == "budget_blocked" for r in rows)
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "budget_blocked" in text
    assert read_jsonl_file(config.layout.pool_jsonl), "候选不得因拦截被丢弃"


def test_auto_chain_subject_to_max_calls_per_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V3：自动链受 M7 单次调用次数上限（max_calls_per_run）约束 —— 硬停 + blocked。"""
    monkeypatch.setenv("OSSLENS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OSSLENS_LLM_BASE_URL", "https://llm.invalid")
    root = seed_workspace(
        tmp_path / "ws", overrides={"depth": {"budget": {"max_calls_per_run": 0}}}
    )
    config = Config.load(root)
    observe(config.layout, make_snapshot(), channel="hot", clock=FixedClock(AS_OF))

    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "fast",
            "--auto-chain",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0
    rows = read_jsonl_file(config.layout.costs_jsonl)
    assert sum(1 for r in rows if r["event"] == "call") == 0
    assert any(r["event"] == "blocked" and r["reason"] == "max_calls_per_run" for r in rows)
    assert read_jsonl_file(config.layout.pool_jsonl), "候选不得因拦截被丢弃"


# --- 频率闸门：auto_chain.min_interval_days（真实分析间隔，不是唤醒频率） -------


def test_auto_chain_min_interval_config_default_and_validation(tmp_path: Path) -> None:
    """X1：默认 7 天；可配置；最小值 1；0 拒绝。"""
    root = seed_workspace(tmp_path / "ws")
    assert Config.load(root).auto_chain.min_interval_days == 7
    tight = Config.from_mapping(root, {"auto_chain": {"min_interval_days": 1}})
    assert tight.auto_chain.min_interval_days == 1
    with pytest.raises(ConfigError):
        Config.from_mapping(root, {"auto_chain": {"min_interval_days": 0}})


def _attributed_call(as_of: str) -> CostEvent:
    return CostEvent(
        event="call",
        repo="o/r",
        depth="fast",
        model="deepseek-flash",
        prompt_tokens=10,
        completion_tokens=5,
        estimated_cost=0.0,
        source="api",
        as_of=as_of,
        run_id="fixed",
        requested_depth="fast",
        actual_depth="fast",
        reason="baseline",
        orchestration_run="43447876155",
    )


def test_auto_interval_gate_only_counts_attributed_calls(tmp_path: Path) -> None:
    """X2：只认自动链 event=call 且带归因；降级/blocked/本地调用不算真实分析。"""
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)

    # 无历史 → 首次放行
    assert last_auto_call_at([]) is None
    assert auto_interval_reached(config, [], now=now) is True

    # 降级行（no_credentials）不是真实分析 → 放行
    downgrade = CostEvent(
        event="downgrade",
        repo="o/r",
        depth="off",
        model="",
        prompt_tokens=0,
        completion_tokens=0,
        estimated_cost=None,
        source="skipped",
        as_of="2026-11-13T00:00:00Z",
        run_id="fixed",
        requested_depth="fast",
        actual_depth="off",
        reason="no_credentials",
        orchestration_run="43447876155",
    )
    assert last_auto_call_at([downgrade]) is None
    assert auto_interval_reached(config, [downgrade], now=now) is True

    # 6 天前 → 未满 7 天 → 跳过
    recent = _attributed_call("2026-11-08T12:00:00Z")
    assert auto_interval_reached(config, [recent], now=now) is False

    # 满 7 天 → 放行
    exact = _attributed_call("2026-11-07T12:00:00Z")
    assert auto_interval_reached(config, [exact], now=now) is True

    # 改小间隔即可放宽频率
    tight = Config.from_mapping(root, {"auto_chain": {"min_interval_days": 1}})
    assert auto_interval_reached(tight, [recent], now=now) is True


def test_auto_interval_segments_are_independent(tmp_path: Path) -> None:
    """Y2：分析段与抽象段各查各的 purpose 锚点，互不占用间隔。"""
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    now = datetime(2026, 11, 14, 12, tzinfo=UTC)

    analysis_call = replace(_attributed_call("2026-11-13T12:00:00Z"), purpose="fast_insight")
    abstract_call = replace(analysis_call, purpose="cluster-abstraction")

    # 抽象段刚跑过 → 抽象段未满；分析段不受影响（放行）
    assert (
        auto_interval_reached(config, [abstract_call], now=now, purposes=AUTO_ABSTRACT_PURPOSES)
        is False
    )
    assert (
        auto_interval_reached(config, [abstract_call], now=now, purposes=AUTO_ANALYSIS_PURPOSES)
        is True
    )

    # 分析段刚跑过 → 分析段未满；抽象段不受影响（放行）
    assert (
        auto_interval_reached(config, [analysis_call], now=now, purposes=AUTO_ANALYSIS_PURPOSES)
        is False
    )
    assert (
        auto_interval_reached(config, [analysis_call], now=now, purposes=AUTO_ABSTRACT_PURPOSES)
        is True
    )


def test_auto_workflow_interval_gate_precedes_analysis_and_abstract() -> None:
    """X2 / Y1：schedule 闸门先于 analyze / 抽象 / 真源回写；skip 分别传递。"""
    raw, doc = _load_auto_workflow()
    gate_at = raw.index("频率闸门")
    assert gate_at < raw.index("first_auto_slug")
    assert gate_at < raw.index("重建站点")
    assert "[skip] interval not reached" in raw
    assert "auto_chain.min_interval_days" in raw
    assert "github.event_name" in raw
    assert "AUTO_ANALYSIS_PURPOSES" in raw
    assert "AUTO_ABSTRACT_PURPOSES" in raw
    # 分析段：analyze + 回写；抽象段：abstract + 回写
    assert raw.count("if: steps.interval.outputs.skip != 'true'") == 4

    analyze_steps = doc["jobs"]["auto-analyze"]["steps"]
    analyze_gate = next(i for i, step in enumerate(analyze_steps) if step.get("id") == "interval")
    analyze_index = next(
        i for i, step in enumerate(analyze_steps) if "自动 analyze" in step["name"]
    )
    assert analyze_gate < analyze_index
    assert analyze_steps[analyze_index]["if"] == "steps.interval.outputs.skip != 'true'"

    abstract_steps = doc["jobs"]["auto-abstract"]["steps"]
    abstract_gate = next(i for i, step in enumerate(abstract_steps) if step.get("id") == "interval")
    abstract_index = next(
        i for i, step in enumerate(abstract_steps) if "独立定时抽象" in step["name"]
    )
    assert abstract_gate < abstract_index
    assert abstract_steps[abstract_index]["if"] == "steps.interval.outputs.skip != 'true'"
