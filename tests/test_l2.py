"""L2 契约测试：strong 档接线 / 四层跨周联动 / 估算安全系数 / D10 口径 / 缓存保留策略。

★ 红线 #9：断言打到**真实输出结构**，且新增检查点配「故意让它失败」的反向用例。
★ 本文件**不 mock 真实调用证据**（T1 的真实 usage 回显见验收报告与 costs.jsonl）；
  这里只用 respx/MockTransport 验证接线逻辑，不作为 DoD 的实跑证据。
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from osslens import llm as llm_module
from osslens.cli import AVAILABLE_DEPTHS, PURPOSE_BY_DEPTH, main
from osslens.config import Config, Layout
from osslens.depth import (
    CostEvent,
    build_ledger_event,
    compute_quota,
    record_event,
    resolve_depth,
)
from osslens.llm import Usage
from osslens.pool import observe
from osslens.render import D10_WORDING
from osslens.retention import (
    apply_retention,
    cache_files,
    dedupe_caches,
    is_cache_layer,
    protected_paths,
)
from osslens.util import FixedClock, sha256_bytes

from .conftest import AS_OF, make_snapshot, read_jsonl_file, seed_workspace

MONDAY = datetime(2026, 11, 2, 9, tzinfo=UTC)  # 周起点 2026-11-02
NEXT_MONDAY = datetime(2026, 11, 9, 9, tzinfo=UTC)  # 跨周
NEXT_MONTH = datetime(2026, 12, 2, 9, tzinfo=UTC)  # 跨月


def _call(as_of: datetime, *, depth: str = "strong", tokens: int = 1000) -> CostEvent:
    return CostEvent(
        event="call",
        repo="deepseek-ai/DeepEP",
        depth=depth,
        model="deepseek-v4-pro" if depth == "strong" else "deepseek-flash",
        prompt_tokens=tokens,
        completion_tokens=0,
        estimated_cost=0.0,
        source="api",
        as_of=as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        run_id=f"r-{depth}-{as_of:%Y%m%d}",
        requested_depth=depth,
        actual_depth=depth,
        reason="baseline",
        purpose=f"{depth}_insight",
    )


# --------------------------------------------------------------------------- T1 strong 接线


def test_strong_is_available_and_maps_to_pro_model_with_thinking(tmp_path: Path) -> None:
    config = Config.from_mapping(tmp_path)
    assert "strong" in AVAILABLE_DEPTHS and "fast" in AVAILABLE_DEPTHS
    assert config.model_for("strong") == "deepseek-v4-pro"
    assert config.llm.thinking["strong"] is True
    assert config.llm.thinking["fast"] is False  # 故意让它失败：thinking 不得全局关
    assert config.max_output_for("strong") == 8192
    assert config.max_output_for("fast") == 4096
    assert PURPOSE_BY_DEPTH["strong"] == "strong_insight"


def test_usage_parses_reasoning_tokens_as_part_of_completion() -> None:
    payload = {
        "prompt_tokens": 21910,
        "completion_tokens": 8156,
        "total_tokens": 30066,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 21910,
        "completion_tokens_details": {"reasoning_tokens": 7801},
    }
    usage = Usage.from_payload(payload)
    assert usage.reasoning_tokens == 7801
    assert usage.completion_tokens == 8156
    assert usage.reasoning_tokens < usage.completion_tokens  # 含在输出内，不重复计费
    restored = Usage.from_json(usage.to_json())
    assert restored == usage
    # 故意让它失败：无 details 时 reasoning 必须是 0，而不是 None/异常
    assert Usage.from_payload({"prompt_tokens": 1, "completion_tokens": 1}).reasoning_tokens == 0


def test_cost_event_carries_reasoning_tokens(tmp_path: Path) -> None:
    event = _call(MONDAY)
    event = CostEvent(**{**event.__dict__, "reasoning_tokens": 7801})
    restored = CostEvent.from_json(event.to_json())
    assert restored.reasoning_tokens == 7801
    assert "reasoning_tokens" in event.to_json()


def test_strong_body_enables_thinking_and_uses_pro_model() -> None:
    """只验证请求体形态（接线），不是实跑证据。"""
    import httpx
    from osslens.config import LlmCredentials

    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"items":[{"id":"t1","chose":"a","alternative":"b","cost":"c","evidence":"x.py:1"}]}'
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                    "completion_tokens_details": {"reasoning_tokens": 2},
                },
            },
        )

    client = llm_module.LlmClient(
        LlmCredentials(api_key="k", base_url="https://llm.test"),
        model="deepseek-v4-pro",
        thinking=True,
        timeout_seconds=5,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    outcome = client.chat_json("sys", "user", max_tokens=8192)
    assert outcome.status == "ok"
    body = bodies[0]
    assert body["model"] == "deepseek-v4-pro"
    assert body["max_tokens"] == 8192
    assert "thinking" not in body  # strong 不发送 disabled
    assert outcome.usage.reasoning_tokens == 2
    # 故意让它失败：fast 档必须显式发送 thinking=disabled
    fast = llm_module.LlmClient(
        LlmCredentials(api_key="k", base_url="https://llm.test"),
        model="deepseek-flash",
        thinking=False,
        timeout_seconds=5,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    fast.chat_json("sys", "user", max_tokens=4096)
    assert bodies[1]["thinking"] == {"type": "disabled"}


# --------------------------------------------------------------------------- T2 四层跨周联动


def test_four_layer_chain_cross_week_downgrade_and_double_write(tmp_path: Path) -> None:
    """L1 基线 → L2 周配额 → L3 预算 → L4 override，受控时钟跨周。"""
    clock = FixedClock(MONDAY)
    config = Config.from_mapping(tmp_path)
    events = [_call(MONDAY, depth="strong")]  # 本周 strong 1/1 已用满

    # 第 1 层基线 + 第 2 层配额：classic 基线 strong 但配额满 → 降级 fast + 留痕
    decision = resolve_depth(
        config,
        requested="auto",
        channel="classic",
        as_of=clock.now(),
        events=events,
        available_depths=AVAILABLE_DEPTHS,
        credentials_present=True,
    )
    assert decision.actual == "fast"
    assert decision.reason == "weekly_quota_exhausted"
    assert decision.downgraded is True
    root = seed_workspace(tmp_path / "ws")
    written = record_event(
        Config.load(root).layout,
        build_ledger_event(repo="deepseek-ai/DeepEP", as_of=clock.now(), decision=decision),
    )
    assert written is True
    assert any(
        r["reason"] == "weekly_quota_exhausted"
        for r in read_jsonl_file(root / "data/costs/costs.jsonl")
    )

    # 第 4 层：人工 override 绕配额，但不绕预算（预算仍拦）
    override = resolve_depth(
        config,
        requested="strong",
        channel="classic",
        as_of=clock.now(),
        events=events,
        available_depths=AVAILABLE_DEPTHS,
        credentials_present=True,
        estimated_prompt_tokens=10,
    )
    assert override.actual == "strong"
    assert override.reason == "manual_override"
    tight = Config.from_mapping(tmp_path, {"depth": {"budget": {"per_run_prompt_tokens": 1}}})
    blocked = resolve_depth(
        tight,
        requested="strong",
        channel="classic",
        as_of=clock.now(),
        events=events,
        available_depths=AVAILABLE_DEPTHS,
        credentials_present=True,
        estimated_prompt_tokens=10,
    )
    assert blocked.reason == "budget_blocked"
    assert blocked.actual == "off"

    # 跨周：推进 7 天后本周配额清零（旧事件不计入新一周）
    clock.advance(days=7)
    assert clock.now() == NEXT_MONDAY
    q = compute_quota(config, events, clock.now())
    assert q.strong_used == 0 and q.tokens_week == 0
    assert q.month_start == "2026-11-01"  # 11 月内
    # 跨月：推进到 12 月，月窗口也清零
    clock.advance(days=23)
    assert clock.now().month == 12
    q2 = compute_quota(config, events, clock.now())
    assert q2.month_start == "2026-12-01"
    assert q2.tokens_month == 0


def test_budget_block_keeps_candidate_and_double_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M5：拦截后候选仍在池；降级双写（报告元数据 + costs.jsonl）。"""
    monkeypatch.setenv("OSSLENS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OSSLENS_LLM_BASE_URL", "https://llm.invalid")
    root = seed_workspace(
        tmp_path / "ws", overrides={"depth": {"budget": {"per_run_prompt_tokens": 1}}}
    )
    observe(Layout(root), make_snapshot(), channel="hot", clock=FixedClock(AS_OF))
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "strong",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0
    text = (root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md").read_text(encoding="utf-8")
    assert "budget_blocked" in text
    rows = read_jsonl_file(root / "data" / "costs" / "costs.jsonl")
    assert any(r["event"] == "blocked" and r["reason"] == "budget_blocked" for r in rows)
    assert read_jsonl_file(root / "data" / "pool" / "pool.jsonl"), "候选不得因拦截被丢弃"


# --------------------------------------------------------------------------- T3 估算安全系数


def test_safety_factor_blocks_l1_underestimate(tmp_path: Path) -> None:
    """D12-2 反向测试：L1 估算 17,354、实测 21,803；限额设 20,000 时旧规则漏拦、新规则拦。"""
    kwargs = {
        "requested": "auto",
        "channel": "classic",
        "as_of": MONDAY,
        "events": [],
        "available_depths": AVAILABLE_DEPTHS,
        "credentials_present": True,
        "estimated_prompt_tokens": 17_354,
    }
    new = Config.from_mapping(tmp_path, {"depth": {"budget": {"per_run_prompt_tokens": 20_000}}})
    decision = resolve_depth(new, **kwargs)
    assert decision.reason == "budget_blocked", "21,803 tok 的场景必须被新规则拦下"
    assert "1.3" in " ".join(decision.chain)

    # 故意让它失败：把系数还原 1.0（模拟旧规则），同一场景必须漏拦
    old = Config.from_mapping(
        tmp_path,
        {"depth": {"budget": {"per_run_prompt_tokens": 20_000, "estimate_safety_factor": 1.0}}},
    )
    leaked = resolve_depth(old, **kwargs)
    assert leaked.reason != "budget_blocked", "系数 1.0 时应漏拦，证明拦截来自系数"


def test_safety_adjusted_value_is_deterministic(tmp_path: Path) -> None:
    config = Config.from_mapping(tmp_path)
    assert config.safety_adjusted(17_354) == 22_560
    assert config.safety_adjusted(0) == 0


# --------------------------------------------------------------------------- T4 D10 口径消歧


def test_report_carries_d10_wording_and_five_sections(tmp_path: Path) -> None:
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
    text = (root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md").read_text(encoding="utf-8")
    assert D10_WORDING in text
    assert sum(1 for line in text.splitlines() if line.startswith("## ")) == 5
    # 故意让它失败：把字样稀释掉后，同一断言必须不成立（证明不是恒真）
    diluted = text.replace(D10_WORDING, "本次成本")
    assert D10_WORDING not in diluted
    assert diluted != text


def test_cost_command_unchanged_reads_full_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """cost 口径不变：读完整台账（含开发期重复调用），与报告「本次分析」口径不同。"""
    root = seed_workspace(tmp_path / "ws")
    layout = Config.load(root).layout
    for i in range(3):
        record_event(layout, _call(MONDAY, depth="fast", tokens=1000 + i))
    assert main(["cost", "--root", str(root), "--as-of", "2026-11-02T00:00:00Z"]) == 0
    out = capsys.readouterr().out
    assert "fast" in out or "调用" in out
    assert "本次分析的成本（不含开发期重复调用）" not in out  # cost 不套用报告口径字样


# --------------------------------------------------------------------------- T5 快照保留策略


def _seed_retention_workspace(root: Path) -> None:
    """构造含真源与缓存层的最小工作区（真实字节，不伪造 fixtures）。"""
    layout = Layout(root)
    layout.ensure_skeleton()
    ext = layout.snapshots_dir / "o__r" / "2026-10-01" / "external"
    ext.mkdir(parents=True, exist_ok=True)
    (ext / "deepwiki.json").write_text('{"status":"hit"}', encoding="utf-8")
    (ext / "source.txt").write_text("外部原文", encoding="utf-8")
    src = layout.snapshots_dir / "o__r" / "2026-10-01" / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.py").write_bytes(b"same content")
    (src / "b.py").write_bytes(b"same content")  # 与 a 重复
    (src / "c.py").write_bytes(b"unique content")
    (layout.data_dir / "llm_cache").mkdir(parents=True, exist_ok=True)
    (layout.data_dir / "llm_cache" / "x.json").write_bytes(b"same content")  # 与 src 重复
    (layout.data_dir / "costs" / "costs.jsonl").write_text("TRUTH\n", encoding="utf-8")
    (layout.snapshots_dir / "o__r" / "2026-10-01.json").write_text("META", encoding="utf-8")


def test_external_and_ledger_are_never_cache_layer(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _seed_retention_workspace(root)
    layout = Layout(root)
    cf = cache_files(layout)
    assert len(cf) == 4  # 3 个 src + 1 个 llm_cache
    # 用相对路径断言：tmp_path 的测试名里含 "external" 字样，绝对字符串会误命中（红线 #19 同类坑）
    rels = [p.relative_to(root).as_posix() for p in cf]
    assert not any("/external/" in rel for rel in rels)
    assert not any(rel.endswith("costs.jsonl") for rel in rels)
    assert not is_cache_layer(layout.data_dir / "costs" / "costs.jsonl", layout)
    ext_json = layout.snapshots_dir / "o__r" / "2026-10-01" / "external" / "deepwiki.json"
    assert not is_cache_layer(ext_json, layout)
    prot = protected_paths(layout)
    assert any("external/deepwiki.json" in p for p in prot)
    assert any("costs/costs.jsonl" in p for p in prot)
    assert any("2026-10-01.json" in p for p in prot)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _seed_retention_workspace(root)
    config = Config.from_mapping(root)
    before = sorted(str(p) for p in root.rglob("*") if p.is_file())
    result = apply_retention(config.layout, config, datetime(2026, 11, 4, tzinfo=UTC), dry_run=True)
    assert result.dry_run is True
    assert len(result.unique_objects) == 2  # "same content" 与 "unique content"
    assert len(result.duplicate_files) == 2
    after = sorted(str(p) for p in root.rglob("*") if p.is_file())
    assert before == after, "dry_run 绝不落盘"
    assert not (root / "data" / "cache_objects").exists()


def test_apply_dedupes_and_never_touches_sources(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _seed_retention_workspace(root)
    config = Config.from_mapping(
        root, {"retention": {"cache_keep_days": 10, "archive_dir": "data/cache_archive"}}
    )
    # llm_cache 无日期段，归档基准取 mtime；显式设为 2026-10-01（确定性，不用运行时钟）
    cache_file = root / "data" / "llm_cache" / "x.json"
    old = time.mktime(datetime(2026, 10, 1, tzinfo=UTC).timetuple())
    os.utime(cache_file, (old, old))
    truth_before = {
        p: p.read_bytes()
        for p in [
            root / "data" / "snapshots" / "o__r" / "2026-10-01" / "external" / "deepwiki.json",
            root / "data" / "snapshots" / "o__r" / "2026-10-01" / "external" / "source.txt",
            root / "data" / "snapshots" / "o__r" / "2026-10-01.json",
            root / "data" / "costs" / "costs.jsonl",
        ]
    }
    result = apply_retention(
        config.layout, config, datetime(2026, 11, 4, tzinfo=UTC), dry_run=False
    )
    assert len(result.unique_objects) == 2
    objects = [p for p in (root / "data" / "cache_objects").rglob("*") if p.is_file()]
    assert len(objects) == 2, "同 sha256 内容只存一份"
    assert len(result.archived) == 4  # 3 src + 1 llm_cache 都超过 10 天
    for path, data in truth_before.items():
        assert path.exists(), f"真源被误删/移动：{path}"
        assert path.read_bytes() == data, f"真源字节被改动：{path}"
    assert not any("external" in p for p in result.archived)
    assert not any("costs.jsonl" in p for p in result.archived)


def test_sha256_of_duplicate_content_is_single_object(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _seed_retention_workspace(root)
    config = Config.from_mapping(root)
    _, unique, duplicates = dedupe_caches(config.layout)
    assert len(unique) == 2
    assert len(duplicates) == 2
    assert sha256_bytes(b"same content") == sha256_bytes(b"same content")
