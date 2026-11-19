"""L0 契约测试：幂等 / as-of 主导 / 稳定 JSON / 零 LLM / 档位闸门 / 留痕。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from osslens.cli import main
from osslens.config import Config
from osslens.depth import (
    CostEvent,
    build_ledger_event,
    load_events,
    record_event,
    resolve_depth,
    summarize,
)
from osslens.util import stable_json

from .conftest import AS_OF, make_snapshot, read_jsonl_file, seed_workspace

REPORT_NAME = "deepseek-ai__DeepEP__2026-11-02.md"


def _config(tmp_path: Path, overrides: dict | None = None) -> Config:
    return Config.from_mapping(tmp_path, overrides or {})


def _call_event(*, depth: str, as_of: str = "2026-11-02T09:00:00Z") -> CostEvent:
    return CostEvent(
        event="call",
        repo="deepseek-ai/DeepEP",
        depth=depth,
        model="m",
        prompt_tokens=1000,
        completion_tokens=500,
        estimated_cost=0.0,
        source="api",
        as_of=as_of,
        run_id="run-1",
        requested_depth=depth,
        actual_depth=depth,
        reason="baseline",
    )


# --------------------------------------------------------------------------- T11 幂等


def test_report_is_byte_identical(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws")
    args = [
        "analyze",
        "deepseek-ai/DeepEP",
        "--root",
        str(root),
        "--no-sources",
        "--as-of",
        "2026-11-02T00:00:00Z",
    ]
    assert main(args) == 0
    report = root / "reports" / REPORT_NAME
    cards = sorted((root / "data" / "featcards").glob("*.json"))
    assert cards, "特征卡未产出"
    first_report = report.read_bytes()
    first_card = cards[0].read_bytes()

    assert main(args) == 0
    assert report.read_bytes() == first_report
    assert sorted((root / "data" / "featcards").glob("*.json"))[0].read_bytes() == first_card


def test_as_of_dominates(tmp_path: Path) -> None:
    """报告时间来自 --as-of，不是运行时钟。"""
    as_of = datetime(2026, 10, 15, tzinfo=UTC)
    root = seed_workspace(tmp_path / "ws", make_snapshot(as_of=as_of))
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--as-of",
            "2026-10-15T00:00:00Z",
        ]
    )
    assert code == 0
    text = (root / "reports" / "deepseek-ai__DeepEP__2026-10-15.md").read_text(encoding="utf-8")
    assert "| 分析基准时间 (as-of) | 2026-10-15T00:00:00Z |" in text
    assert "2026-11-02" not in text


def test_stable_json_is_sorted() -> None:
    assert stable_json({"b": 1, "a": {"d": 1, "c": 2}}) == (
        '{\n  "a": {\n    "c": 2,\n    "d": 1\n  },\n  "b": 1\n}'
    )


# --------------------------------------------------------------------------- T8 零 LLM


def test_no_llm_involved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """off 档零 LLM 的**取证**：拦截真实网络出口，断言一次请求都没发出。

    与"mock 掉 LLM 客户端再断言调用 0 次"不同：这里 patch 的是 httpx 的传输层，
    任何模块、任何客户端的真实外发都会经过它。
    """
    root = seed_workspace(tmp_path / "ws")
    egress: list[str] = []
    original = httpx.HTTPTransport.handle_request

    def spy(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        egress.append(str(request.url))
        return original(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", spy)

    # 情形 1：无任何凭据
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

    # 情形 2：凭据齐全但显式请求 off（L2 起 strong 已接入，auto+凭据会合法地发起调用，
    # 因此"off 档零 LLM"必须用 --depth off 显式取证，不能靠档位碰巧不可用）。
    monkeypatch.setenv("OSSLENS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OSSLENS_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("OSSLENS_LLM_MODEL", "test-model")
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "off",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0

    assert egress == [], f"off 档检测到真实外发请求：{egress}"


def test_llm_endpoint_only_in_llm_module() -> None:
    """端点路径只允许出现在 `llm.py`；其它模块不得自带模型服务商端点。"""
    import osslens

    package = Path(osslens.__file__).parent
    markers = ("chat/completions", "api.openai.com", "api.anthropic.com", "generativelanguage")
    for path in sorted(package.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if path.name == "llm.py" and marker == "chat/completions":
                continue
            assert marker not in text, f"{path.name} 出现模型端点字面量 {marker}"


# --------------------------------------------------------------------------- T9 降级留痕


def test_no_credentials_falls_back_to_off(tmp_path: Path) -> None:
    config = _config(tmp_path)
    decision = resolve_depth(
        config,
        requested="auto",
        channel="classic",
        as_of=AS_OF,
        events=[],
        available_depths=frozenset({"fast", "strong"}),
    )
    assert decision.actual == "off"
    assert decision.reason == "no_credentials"
    assert decision.downgraded is True


def test_quota_downgrade_is_recorded(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws", overrides={"depth": {"weekly_quota": {"strong": 0}}})
    config = Config.load(root)
    events = [_call_event(depth="strong")]
    decision = resolve_depth(
        config,
        requested="auto",
        channel="classic",
        as_of=AS_OF,
        events=events,
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
    )
    assert decision.actual == "fast"
    assert decision.reason == "weekly_quota_exhausted"
    assert decision.downgraded is True

    written = record_event(
        config.layout, build_ledger_event(repo="deepseek-ai/DeepEP", as_of=AS_OF, decision=decision)
    )
    assert written is True
    records = read_jsonl_file(config.layout.costs_jsonl)
    assert [row["event"] for row in records] == ["downgrade"]
    assert records[0]["reason"] == "weekly_quota_exhausted"
    assert records[0]["actual_depth"] == "fast"
    # 重跑不重复追加（append-only + 幂等）
    duplicate = record_event(
        config.layout, build_ledger_event(repo="deepseek-ai/DeepEP", as_of=AS_OF, decision=decision)
    )
    assert duplicate is False
    assert len(read_jsonl_file(config.layout.costs_jsonl)) == 1


def test_budget_gate_cannot_be_overridden(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        {
            "depth": {
                "budget": {
                    "weekly_tokens": 1_000_000,
                    "monthly_tokens": 3_000_000,
                    "per_run_prompt_tokens": 100,
                }
            }
        },
    )
    decision = resolve_depth(
        config,
        requested="strong",
        channel="classic",
        as_of=AS_OF,
        events=[],
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
        estimated_prompt_tokens=500,
    )
    assert decision.actual == "off"
    assert decision.reason == "budget_blocked"
    assert any("L4 也不能绕过" in step for step in decision.chain)


def test_manual_override_bypasses_quota_but_not_budget(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        {"depth": {"weekly_quota": {"strong": 0, "fast": 0}}},
    )
    decision = resolve_depth(
        config,
        requested="strong",
        channel="classic",
        as_of=AS_OF,
        events=[_call_event(depth="strong")],
        available_depths=frozenset({"fast", "strong"}),
        credentials_present=True,
        estimated_prompt_tokens=10,
    )
    assert decision.actual == "strong"
    assert decision.reason == "manual_override"
    assert decision.downgraded is False


def test_downgrade_is_double_written(tmp_path: Path) -> None:
    """报告元数据块 + costs.jsonl，两处都必须有（红线 #10）。"""
    root = seed_workspace(tmp_path / "ws")
    assert (
        main(
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
        == 0
    )
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "| 请求档位 (requested_depth) | auto |" in text
    assert "| **实际档位** (actual_depth) | off（降级" in text
    assert "| 降级原因 (reason) | no_credentials" in text
    assert "| 配额状态 (quota_state) | strong 0/1、fast 0/3" in text

    costs = root / "data" / "costs" / "costs.jsonl"
    records = read_jsonl_file(costs)
    assert len(records) == 1
    assert records[0]["event"] == "downgrade"
    assert records[0]["reason"] == "no_credentials"
    assert records[0]["requested_depth"] == "auto"


# --------------------------------------------------------------------------- 报告结构


def test_report_has_six_modules_and_appendices_in_order(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws")
    assert (
        main(
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
        == 0
    )
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    headings = [
        "## 导读",
        "## 1. 项目定位与目标",
        "## 2. 架构全景",
        "## 3. 核心抽象与契约",
        "## 4. 关键设计决策（ADR）",
        "## 5. 扩展与改造路径",
        "## 6. 经验卡",
        "## 附录 A 证据索引与未知项",
        "## 附录 B 许可证 / 维护 / 工程 / 成本",
    ]
    positions = [text.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert sum(1 for line in text.splitlines() if line.startswith("## ")) == len(headings)

    adr = text.split("## 4. 关键设计决策（ADR）", 1)[1].split("## 5.", 1)[0]
    assert "[未获得]" in adr, "off 档必须显式写未获得，不得留空或编造"
    assert "### A2. 外部资料" in text
    assert "### B4. 运行元数据与成本" in text


# --------------------------------------------------------------------------- 其他


def test_init_creates_skeleton_and_never_overwrites(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    assert main(["init", "--root", str(root)]) == 0
    assert (root / "config.yaml").exists()
    assert (root / "patterns" / "seed.yaml").exists()
    for sub in ("ledger", "pool", "snapshots", "featcards", "costs"):
        assert (root / "data" / sub).is_dir()
    assert (root / "reports").is_dir()

    (root / "config.yaml").write_text("# 用户改动\n", encoding="utf-8")
    assert main(["init", "--root", str(root)]) == 0
    assert (root / "config.yaml").read_text(encoding="utf-8") == "# 用户改动\n"


def test_cost_summary_counts_week_and_month(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    record_event(config.layout, _call_event(depth="strong", as_of="2026-11-02T09:00:00Z"))
    # 2026-11-01 是周日：属于本月，但不属于 11-02 那一周
    record_event(config.layout, _call_event(depth="fast", as_of="2026-11-01T09:00:00Z"))
    summary = summarize(config, load_events(config.layout), as_of=AS_OF)
    assert summary.week_tokens == 1500
    assert summary.month_tokens == 3000
    assert summary.by_depth == {"strong": 1}
    assert summary.budget_week_remaining == config.depth.budget.weekly_tokens - 1500


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws")
    before = sorted(path.as_posix() for path in root.rglob("*") if path.is_file())
    assert (
        main(
            [
                "analyze",
                "deepseek-ai/DeepEP",
                "--root",
                str(root),
                "--no-sources",
                "--as-of",
                "2026-11-02T00:00:00Z",
                "--dry-run",
            ]
        )
        == 0
    )
    after = sorted(path.as_posix() for path in root.rglob("*") if path.is_file())
    assert before == after


def test_explicit_off_has_no_downgrade_event(tmp_path: Path) -> None:
    """显式 off 不是降级，不应写 downgrade；但报告仍要五区块齐全。"""
    root = seed_workspace(tmp_path / "ws")
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "off",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "| 请求档位 (requested_depth) | off |" in text
    assert "| 降级原因 (reason) | explicit_off" in text
    assert read_jsonl_file(root / "data" / "costs" / "costs.jsonl") == []


def test_missing_config_exits_1(tmp_path: Path) -> None:
    assert main(["analyze", "deepseek-ai/DeepEP", "--root", str(tmp_path)]) == 1


def test_bad_slug_exits_2(tmp_path: Path) -> None:
    root = seed_workspace(tmp_path / "ws")
    assert main(["analyze", "bad-slug", "--root", str(root)]) == 2


def test_cost_command_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = seed_workspace(tmp_path / "ws")
    assert main(["cost", "--root", str(root), "--as-of", "2026-11-02T00:00:00Z"]) == 0
    output = capsys.readouterr().out
    assert "本周（起 2026-11-02）" in output
    assert "本月（起 2026-11-01）" in output
    assert "降级 0 次" in output


def test_eligible_command_reports_exclusion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from osslens.config import Layout
    from osslens.pool import observe
    from osslens.util import FixedClock

    root = seed_workspace(tmp_path / "ws")
    layout = Layout(root)
    observe(layout, make_snapshot(), channel="hot", clock=FixedClock(AS_OF))
    assert main(["pool", "eligible", "--root", str(root), "--as-of", "2026-11-02T00:00:00Z"]) == 0
    output = capsys.readouterr().out
    assert "深挖候选（as-of 2026-11-02T00:00:00Z）：0 个" in output
    assert "观察期未满：已观测 0 天，还差 7 天" in output


def test_duplicate_ledger_rows_count_once(tmp_path: Path) -> None:
    """台账里同一 run_id 的重复行不得让降级次数翻倍（读取侧去重）。"""
    from osslens.config import Layout

    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    layout: Layout = config.layout
    record_event(layout, _call_event(depth="strong"))
    event = build_ledger_event(
        repo="deepseek-ai/DeepEP",
        as_of=AS_OF,
        decision=resolve_depth(
            config,
            requested="auto",
            channel="classic",
            as_of=AS_OF,
            events=[],
            available_depths=frozenset({"fast", "strong"}),
            credentials_present=False,
        ),
    )
    assert record_event(layout, event) is True
    # 模拟修复前遗留的重复行（直接追加，绕过幂等写入）
    from osslens.util import append_jsonl

    append_jsonl(layout.costs_jsonl, event.to_json())
    summary = summarize(config, load_events(layout), as_of=AS_OF)
    assert summary.week_downgrades == 1
    assert len(read_jsonl_file(layout.costs_jsonl)) == 3


def test_featcard_has_deps_graph_shape(tmp_path: Path) -> None:
    """L0 不渲染 Mermaid，但 §6.5 的 deps.graph 数据结构必须已产出。"""
    import json

    root = seed_workspace(tmp_path / "ws")
    assert (
        main(
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
        == 0
    )
    card_file = next((root / "data" / "featcards").glob("*.json"))
    card = json.loads(card_file.read_text(encoding="utf-8"))
    graph = card["deps"]["graph"]
    assert graph["nodes"] == [] and graph["edges"] == []
    assert "truncated" in graph
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "```mermaid" in text, "L1 起报告必须内嵌 Mermaid 代码块"
    assert "无可提取的内部模块依赖边" in text, "无源码切片时走 §6.5 的显式空态"


def test_report_v2_has_reader_modules_and_appendix(tmp_path: Path) -> None:
    """v2a：正文是 6 个可读模块，参数表下沉到附录；正文不再先甩元数据表。"""
    root = seed_workspace(tmp_path / "ws")
    assert (
        main(
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
        == 0
    )
    text = (root / "reports" / REPORT_NAME).read_text(encoding="utf-8")
    assert "## 导读" in text
    assert "> 阅读档位：架构学习（profile=architecture_learning）" in text
    assert "证据约定：[事实]" in text
    for heading in (
        "## 1. 项目定位与目标",
        "## 2. 架构全景",
        "## 3. 核心抽象与契约",
        "## 4. 关键设计决策（ADR）",
        "## 5. 扩展与改造路径",
        "## 6. 经验卡",
    ):
        assert heading in text
    body = text.split("## 附录 A", 1)[0]
    assert "| 项 | 值 |" not in body, "运行元数据表必须下沉到附录"
    assert "| 指标 | 值 |" not in body, "体检事实表必须下沉到附录"
    assert "[未获得]" in text, "缺数据必须显式标注，不能用通用描述补空"
    assert "通常" not in text and "一般来说" not in text
    assert "不能替代法务审查" not in text  # v3 不再给「可商用」类结论
    assert "不给出「可商用」结论" in text
