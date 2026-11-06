"""L3 契约测试：domains/阈值、三态召回、四层 schema、ops、自检四问、编排与成本闸门。

★ 红线 #9：断言打真实输出结构；每个检查点配「故意让它失败」的反向用例。
★ 本文件的样本是 **tests/ 内的结构化夹具**，绝不写进 `patterns/*.yaml` 真源（S4）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from osslens import patterns as p
from osslens.abstract import (
    STATUS_BUDGET_BLOCKED,
    STATUS_COMPLETED,
    STATUS_INSUFFICIENT,
    STATUS_NO_CREDENTIALS,
    TYPE_CLUSTER,
    TYPE_RECONCILE,
    CachedModelCaller,
    ModelResult,
    RunRecord,
    append_run,
    budget_gate,
    cluster_run,
    l2_summary,
    load_runs,
    load_samples,
    run_id_for,
)
from osslens.cli import main
from osslens.config import Config, Layout
from osslens.depth import EVENT_CALL, load_events
from osslens.llm import estimate_tokens
from osslens.util import ConfigError, fmt_iso, parse_iso, stable_json

from .conftest import AS_OF, write_config

LATER = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- 夹具


def _card(repo: str, *, cache: bool = False, parallel: bool = False) -> dict[str, Any]:
    return {
        "identity": {"repo": repo, "commit": "a" * 40, "analyzed_at": fmt_iso(LATER)},
        "parallel": {
            "hits": {"TP": parallel, "EP": False},
            "evidence": {"TP": [{"file": "src/parallel.py", "line": 12, "snippet": "x"}]},
        },
        "cache": {
            "hits": {"paged": cache, "radix": False},
            "evidence": {"paged": [{"file": "src/cache.py", "line": 7, "snippet": "y"}]},
        },
        "hardware": {"vendors": ["NVIDIA"], "arch_gates": [], "kernel_langs": ["Cuda"]},
        "governance": {"org_type": "Organization", "license": "MIT", "has_governance_docs": True},
    }


def _workspace(
    tmp_path: Path, *, n_samples: int = 0, overrides: dict[str, Any] | None = None
) -> Config:
    layout = Layout(tmp_path)
    layout.ensure_skeleton()
    write_config(tmp_path, overrides)
    for index in range(n_samples):
        repo = f"test-org/inference-{index}"
        path = layout.featcards_dir / f"test-org__inference-{index}__{'a' * 40}.json"
        path.write_text(json.dumps(_card(repo, cache=index % 2 == 0)), encoding="utf-8")
    return Config.load(tmp_path)


def _entry(
    entry_id: str,
    level: str = "L2",
    **kwargs: Any,
) -> p.PatternEntry:
    defaults: dict[str, Any] = {
        "cluster": "inference",
        "statement": "前缀重叠高时采用复用",
        "tags": ("cache.hits.paged",),
        "counterexamples": (p.Evidence(repo="test-org/inference-1", kind="反例"),),
        "cross_domains": ("inference", "ai_infra"),
        "boundaries": ("适用于自回归解码",),
        "anti_patterns": ("无对照组却断言普适",),
        "drilldown": ("P-L3", "P-L2", "P-L1"),
    }
    defaults.update(kwargs)
    return p.PatternEntry(id=entry_id, level=level, **defaults)


def _l1() -> p.PatternEntry:
    return p.PatternEntry(
        id="P-L1",
        level="L1",
        cluster="inference",
        statement="存在 paged cache 实现",
        evidence=(p.Evidence(repo="test-org/inference-0", kind="正例", path="src/cache.py:7"),),
    )


def _l2() -> p.PatternEntry:
    return p.PatternEntry(
        id="P-L2",
        level="L2",
        cluster="inference",
        statement="前缀重叠高时采用复用",
        tags=("cache.hits.paged",),
        counterexamples=(p.Evidence(repo="test-org/inference-1", kind="反例"),),
    )


def _l3() -> p.PatternEntry:
    return p.PatternEntry(
        id="P-L3",
        level="L3",
        cluster="inference",
        statement="跨域：缓存复用是通用范式",
        cross_domains=("inference", "ai_infra"),
    )


def _l4() -> p.PatternEntry:
    return _entry(
        "P-L4",
        level="L4",
        drilldown=("P-L3", "P-L2", "P-L1"),
    )


# --------------------------------------------------------------------------- T1 配置


def test_domains_and_four_thresholds_are_configurable(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    assert config.domain_ids == ("agent", "ai_infra", "inference", "training")
    assert config.abstract.cluster_min_new_projects == 6
    assert config.abstract.cross_domain_min_l2_entries == 8
    assert config.abstract.cross_domain_every_cluster_runs == 4
    assert config.abstract.reconcile_every_incremental_runs == 5
    assert not (tmp_path / "scope.yaml").exists()
    assert config.domain_for("vllm-project/vllm") == "inference"
    assert config.domain_for("unknown/unmatched") is None  # 故意让它失败：不得猜簇


def test_thresholds_come_from_config_not_code(tmp_path: Path) -> None:
    config = _workspace(
        tmp_path,
        overrides={
            "abstract": {"cluster_min_new_projects": 3, "reconcile_every_incremental_runs": 2}
        },
    )
    assert config.abstract.cluster_min_new_projects == 3
    assert config.abstract.reconcile_every_incremental_runs == 2


def test_non_positive_threshold_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        _workspace(tmp_path, overrides={"abstract": {"cluster_min_new_projects": 0}})


def test_duplicate_domain_id_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        _workspace(
            tmp_path,
            overrides={
                "domains": [{"id": "x", "match_any": ["a"]}, {"id": "x", "match_any": ["b"]}]
            },
        )


# --------------------------------------------------------------------------- T3 零 LLM 三态召回


def test_three_class_output() -> None:
    full_features = tuple(p.flatten_featcard(_card("test-org/inference-0", cache=True)))
    entry = _l2()
    # 故意让它失败：标签必须与正例特征完全重合才会命中，否则三态缺一态
    entry = p.PatternEntry(
        id=entry.id,
        level=entry.level,
        cluster=entry.cluster,
        statement=entry.statement,
        tags=full_features,
        counterexamples=entry.counterexamples,
    )
    projects = (
        p.ProjectFeatures.from_card(_card("test-org/inference-0", cache=True), "inference"),
        p.ProjectFeatures(
            repo="test-org/inference-1", domain="inference", features=(), soft_labels=()
        ),
        p.ProjectFeatures.from_card(_card("other/thing"), "agent"),
    )
    result = p.recall(projects, (entry,), similarity_threshold=0.3)
    states = {row.state for row in result.rows}
    assert states == {
        p.STATE_MATCHED,
        p.STATE_NEW_CANDIDATE,
        p.STATE_NOT_APPLICABLE,
    }, states
    assert all(row.state in p.RECALL_STATES for row in result.rows)


def test_not_applicable_when_domain_mismatch() -> None:
    projects = (p.ProjectFeatures.from_card(_card("other/thing"), "agent"),)
    result = p.recall(projects, (_l2(),))
    row = result.rows[0]
    assert row.state == p.STATE_NOT_APPLICABLE
    assert result.candidates[0].scope_mismatch is True  # 设计方案 §4.1：丢弃，不挂条目
    assert result.candidates[0].pattern_id == ""


def test_new_candidate_generates_attachable_counterexample() -> None:
    projects = (p.ProjectFeatures.from_card(_card("test-org/inference-1"), "inference"),)
    result = p.recall(projects, (_l2(),), similarity_threshold=0.9)
    assert result.rows[0].state == p.STATE_NEW_CANDIDATE
    assert any(not item.scope_mismatch for item in result.candidates)


def test_recall_deterministic_and_byte_identical() -> None:
    projects = tuple(
        p.ProjectFeatures.from_card(_card(f"test-org/inference-{i}", cache=True), "inference")
        for i in range(5)
    )
    entries = (_l2(), _l3())
    first = p.recall(projects, entries)
    second = p.recall(list(reversed(projects)), list(reversed(entries)))
    assert stable_json([row.to_json() for row in first.rows]) == stable_json(
        [row.to_json() for row in second.rows]
    )
    assert stable_json([item.to_json() for item in first.candidates]) == stable_json(
        [item.to_json() for item in second.candidates]
    )


def test_weighted_jaccard_is_weighted_and_bounded() -> None:
    assert p.weighted_jaccard(("parallel.hits.TP",), ()) == 0.0
    assert p.weighted_jaccard((), ()) == 0.0
    plain = p.weighted_jaccard(("cache.hits.paged", "x"), ("cache.hits.paged", "y"))
    weighted = p.weighted_jaccard(
        ("cache.hits.paged", "x"), ("cache.hits.paged", "y"), {"cache": 3.0}
    )
    assert weighted > plain  # 故意让它失败：权重没生效则相等
    assert 0.0 <= plain <= 1.0


def test_zero_llm_recall_has_no_http_and_no_endpoint_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """传输层拦截：召回路径根本不发请求；静态：新模块不含模型端点字面量。"""
    import osslens

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("召回路径发起了 HTTP 请求")

    monkeypatch.setattr(httpx.Client, "request", boom)
    monkeypatch.setattr(httpx.Client, "send", boom)
    result = p.recall(
        (p.ProjectFeatures.from_card(_card("test-org/inference-0", cache=True), "inference"),),
        (_l2(),),
    )
    assert result.rows

    package = Path(osslens.__file__).parent
    for name in ("patterns.py", "abstract.py"):
        text = (package / name).read_text(encoding="utf-8")
        for marker in ("chat/completions", "api.openai.com", "api.anthropic.com"):
            assert marker not in text, f"{name} 出现模型端点字面量 {marker}"


def test_featcard_flatten_and_soft_labels_are_sorted() -> None:
    features = p.flatten_featcard(_card("x/y", cache=True, parallel=True))
    assert features == tuple(sorted(features))
    assert "cache.hits.paged" in features
    assert "parallel.hits.TP" in features
    labels = p.soft_labels_for(features)
    assert labels == tuple(sorted(labels))
    assert "cache-reuse" in labels and "sharding" in labels
    evidence = p.code_evidence_from_card(_card("x/y", cache=True), "x/y")
    assert evidence[0].path == "src/cache.py:7"


# --------------------------------------------------------------------------- T4 四层 schema


def test_l2_requires_counterexample_slot() -> None:
    assert p.validate_entry(_l2()) == ()
    broken = p.PatternEntry(
        id="P-BAD", level="L2", cluster="inference", statement="无反例", source="real"
    )
    problems = p.validate_entry(broken)
    assert any("反例位" in text for text in problems)  # 故意让它失败：缺反例位必须被拒


def test_l3_requires_two_cross_domain_evidence() -> None:
    assert p.validate_entry(_l3()) == ()
    broken = p.PatternEntry(
        id="P-BAD",
        level="L3",
        cluster="inference",
        statement="单方向",
        cross_domains=("inference",),
    )
    assert any("跨域" in text for text in p.validate_entry(broken))


def test_l4_drilldown_chain_must_reach_l1_code_evidence() -> None:
    library = (_l1(), _l2(), _l3(), _l4())
    assert p.validate_library(library) == ()
    broken = p.PatternEntry(
        id="P-BAD",
        level="L4",
        cluster="inference",
        statement="本质论，无下钻",
        boundaries=("b",),
        anti_patterns=("a",),
        drilldown=(),
    )
    assert p.validate_drilldown(broken, {item.id: item for item in library}) != ()
    # 故意让它失败：链末端 L1 没有 file:line → 拒绝
    no_evidence = p.PatternEntry(
        id="P-L1-BAD", level="L1", cluster="inference", statement="无代码证据"
    )
    index = {item.id: item for item in library}
    index["P-L1-BAD"] = no_evidence
    chain_missing = p.PatternEntry(
        id="P-BAD2",
        level="L4",
        cluster="inference",
        statement="链末端无证据",
        boundaries=("b",),
        anti_patterns=("a",),
        drilldown=("P-L3", "P-L2", "P-L1-BAD"),
    )
    assert p.validate_drilldown(chain_missing, index) != ()


def test_control_group_required_for_breakout_claim() -> None:
    ok = _entry(
        "P-OK",
        claim_kind="breakout_gene",
        control_group=("other/similar-but-not-hot",),
        counterexamples=(p.Evidence(repo="other/similar-but-not-hot", kind="反例"),),
    )
    assert p.validate_entry(ok) == ()
    broken = _entry("P-BAD", claim_kind="breakout_gene")
    problems = p.validate_entry(broken)
    assert any("对照组" in text for text in problems)  # 故意让它失败：缺对照组被拒


def test_synthetic_entry_cannot_be_written_to_truth(tmp_path: Path) -> None:
    path = tmp_path / "library.yaml"
    synthetic = _entry("P-SYN", source="synthetic")
    with pytest.raises(p.PatternError, match="合成"):
        p.save_library(path, (synthetic,))
    assert not path.exists()  # 真源纯净：一个字节都没写


def test_save_library_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "library.yaml"
    p.save_library(path, (_l1(), _l2()))
    with pytest.raises(p.PatternError, match="append-only"):
        p.save_library(path, (_l1(),))  # 故意让它失败：旧 id 丢失即违规
    assert {item.id for item in p.load_library(path)} == {"P-L1", "P-L2"}


# --------------------------------------------------------------------------- T5 ops / reconcile


def test_six_ops_and_falsified_never_deleted() -> None:
    base = (_l1(), _l2(), _l3())
    ops = (
        p.Op(op="add", id="P-NEW", entry=_entry("P-NEW")),
        p.Op(op="strengthen", id="P-L2", evidence=(p.Evidence(repo="r", kind="正例"),)),
        p.Op(op="weaken", id="P-L2", evidence=(p.Evidence(repo="r2", kind="反例"),)),
        p.Op(op="refine", id="P-L2", statement="收窄后的陈述"),
        p.Op(op="falsify", id="P-L3"),
        p.Op(op="merge", id="P-L2", target_id="P-NEW"),
    )
    assert {item.op for item in ops} == set(p.OPS)
    result, warnings = p.apply_ops(base, ops)
    assert warnings == ()
    ids = {item.id for item in result}
    assert "P-L3" in ids  # falsified 不删
    assert next(item for item in result if item.id == "P-L3").status == "falsified"
    assert "P-NEW" in next(item for item in result if item.id == "P-L2").aliases


def test_reconcile_every_five_incremental_runs() -> None:
    assert not p.needs_reconcile(4, 5)
    assert p.needs_reconcile(5, 5)
    assert p.needs_reconcile(10, 5)
    assert p.should_cross_domain(8, 0, min_entries=8, every_runs=4)
    assert p.should_cross_domain(0, 4, min_entries=8, every_runs=4)
    assert not p.should_cross_domain(1, 1, min_entries=8, every_runs=4)


# --------------------------------------------------------------------------- T6 自检四问


def test_self_check_answers_four_questions_and_warns_on_no_counterexample() -> None:
    empty = p.build_self_check((), ())
    assert empty.has_drilldown_evidence is False
    assert empty.new_counterexamples == 0
    assert empty.has_cross_domain_evidence is False
    assert empty.manual_review_target  # 抽检位必填
    assert any("幸存者偏差" in text for text in empty.warnings)

    full = p.build_self_check(
        (_l1(), _l2(), _l3()),
        (
            p.CounterexampleCandidate(
                project="r", pattern_id="P-L2", reason="x", scope_mismatch=False
            ),
        ),
    )
    assert full.has_drilldown_evidence is True
    assert full.new_counterexamples == 1
    assert full.has_cross_domain_evidence is True
    assert full.manual_review_target == "P-L1"


# --------------------------------------------------------------------------- T8/T9 编排


def test_insufficient_samples_is_legal_terminal_state_with_zero_output(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=2)
    result = cluster_run(config, as_of=LATER, off=True)
    record = result.record
    assert record.status == STATUS_INSUFFICIENT
    assert record.ops == ()
    assert record.produced_patterns == ()
    assert record.llm_calls == 0
    assert result.appended is True
    assert any("样本 2 < 6" in text for text in record.warnings)
    assert (
        not config.layout.library_patterns.exists()
        or p.load_library(config.layout.library_patterns) == ()
    )
    assert not list(config.layout.data_dir.glob("llm_cache/abstract-*.json"))


def test_run_record_has_all_nine_required_fields(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=2)
    record = cluster_run(config, as_of=LATER, off=True).record
    payload = record.to_json()
    for key in (
        "run_id",
        "type",
        "cluster",
        "trigger",
        "input_projects",
        "input_patterns",
        "ops",
        "llm_calls",
        "created_at",
    ):
        assert key in payload
    assert record.created_at == fmt_iso(LATER)  # 时间来自 as-of，不是运行时钟
    assert RunRecord.from_json(payload).run_id == record.run_id


def test_cluster_run_is_idempotent_and_replayable(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=2)
    first = cluster_run(config, as_of=LATER, off=True)
    second = cluster_run(config, as_of=LATER, off=True)
    assert first.record.run_id == second.record.run_id
    assert second.appended is False
    assert second.record.llm_calls == 0
    assert len(load_runs(config.layout)) == 1
    assert second.warnings  # 重放提示


def test_run_id_is_deterministic() -> None:
    a = run_id_for(run_type=TYPE_CLUSTER, cluster="inference", as_of=LATER, projects=("a", "b"))
    b = run_id_for(run_type=TYPE_CLUSTER, cluster="inference", as_of=LATER, projects=("b", "a"))
    assert a == b
    assert a != run_id_for(
        run_type=TYPE_RECONCILE, cluster="inference", as_of=LATER, projects=("a", "b")
    )


def test_load_samples_reports_classification_gap(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=1)
    path = config.layout.featcards_dir / "zz__unmatched__c.json"
    path.write_text(json.dumps(_card("zz/unmatched")), encoding="utf-8")
    samples, uncovered = load_samples(config.layout, config)
    assert len(samples) == 2
    assert uncovered == ("zz/unmatched",)  # 不自行补规则


def test_incremental_run_does_not_refeed_all_samples(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=12)
    layout = config.layout
    previous = tuple(f"test-org/inference-{i}" for i in range(6))
    append_run(
        layout,
        RunRecord(
            run_id="prev",
            type=TYPE_CLUSTER,
            cluster="inference",
            trigger="prev",
            input_projects=previous,
            input_patterns=(),
            ops=(),
            llm_calls=1,
            created_at=fmt_iso(AS_OF),
            status=STATUS_COMPLETED,
            self_check=p.build_self_check((), ()),
            produced_patterns=("P-1",),
        ),
    )
    result = cluster_run(config, as_of=LATER, off=True)
    assert result.record.type == TYPE_CLUSTER
    assert len(result.record.input_projects) == 6
    assert not set(result.record.input_projects) & set(previous)  # 只喂新增样本


def test_reconcile_after_five_incremental_runs_feeds_all_samples(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=7)
    layout = config.layout
    for index in range(5):
        append_run(
            layout,
            RunRecord(
                run_id=f"prev-{index}",
                type=TYPE_CLUSTER,
                cluster="inference",
                trigger="prev",
                input_projects=(f"test-org/inference-{index}",),
                input_patterns=(),
                ops=(),
                llm_calls=1,
                created_at=fmt_iso(AS_OF),
                status=STATUS_COMPLETED,
                self_check=p.build_self_check((), ()),
                produced_patterns=("P-1",),
            ),
        )
    result = cluster_run(config, as_of=LATER, off=True)
    assert result.record.type == TYPE_RECONCILE
    assert len(result.record.input_projects) == 7  # 全量 reconcile


def test_off_mode_never_calls_model_or_writes_call_event(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=6)
    result = cluster_run(config, as_of=LATER, off=True)
    assert result.record.status == STATUS_NO_CREDENTIALS
    assert result.record.llm_calls == 0
    assert all(item.event != EVENT_CALL for item in load_events(config.layout))


def test_budget_gate_uses_safety_factor(tmp_path: Path) -> None:
    config = _workspace(
        tmp_path,
        overrides={
            "depth": {"budget": {"per_run_prompt_tokens": 100, "estimate_safety_factor": 1.3}}
        },
    )
    ok, _ = budget_gate(config, as_of=LATER, estimated_prompt_tokens=70)  # 70*1.3=91
    blocked, reason = budget_gate(config, as_of=LATER, estimated_prompt_tokens=80)  # 104
    assert ok is True
    assert blocked is False
    assert "100" in reason


def test_budget_blocked_is_legal_terminal_state(tmp_path: Path) -> None:
    config = _workspace(
        tmp_path,
        n_samples=6,
        overrides={"depth": {"budget": {"per_run_prompt_tokens": 1}}},
    )
    result = cluster_run(config, as_of=LATER)
    assert result.record.status == STATUS_BUDGET_BLOCKED
    assert result.record.llm_calls == 0
    assert result.record.ops == ()


def test_l2_summary_is_structured_and_compact() -> None:
    library = (_l1(), _l2(), _l3(), _l4())
    summary = l2_summary(library)
    assert "P-L2" in summary and "P-L1" not in summary
    assert "src/cache.py" not in summary  # 不回显源码/证据正文
    assert estimate_tokens(summary) < estimate_tokens(stable_json([e.to_json() for e in library]))


def test_cached_caller_does_not_duplicate_call(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    layout.ensure_skeleton()

    class Fake:
        calls = 0

        def __call__(self, *, system: str, user: str) -> ModelResult:
            self.calls += 1
            return ModelResult(
                ops=(),
                prompt_tokens=10,
                completion_tokens=5,
                cache_hit_tokens=0,
                calls=1,
                status="ok",
                reason="",
                model="deepseek-flash",
            )

    inner = Fake()
    cached = CachedModelCaller(inner, layout)
    first = cached(system="s", user="u")
    second = cached(system="s", user="u")
    assert inner.calls == 1
    assert first.calls == 1
    assert second.calls == 0 and second.status == "cache_hit"


def test_model_call_records_usage_and_applies_ops(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=6)
    p.save_library(config.layout.library_patterns, (_l1(), _l2()))

    class Fake:
        def __call__(self, *, system: str, user: str) -> ModelResult:
            return ModelResult(
                ops=(
                    p.Op(
                        op="strengthen",
                        id="P-L2",
                        evidence=(p.Evidence(repo="test-org/inference-0", kind="正例"),),
                    ),
                ),
                prompt_tokens=100,
                completion_tokens=50,
                cache_hit_tokens=0,
                calls=1,
                status="ok",
                reason="",
                model="deepseek-flash",
            )

    result = cluster_run(config, as_of=LATER, caller=Fake())
    assert result.record.status == STATUS_COMPLETED
    assert result.record.llm_calls == 1
    events = [item for item in load_events(config.layout) if item.event == EVENT_CALL]
    assert len(events) == 1
    assert events[0].prompt_tokens == 100 and events[0].completion_tokens == 50
    assert events[0].purpose == TYPE_CLUSTER
    stored = p.load_library(config.layout.library_patterns)
    assert next(item for item in stored if item.id == "P-L2").revision == 2
    ops_log = config.layout.ops_jsonl.read_text(encoding="utf-8").splitlines()
    assert len(ops_log) == 1


# --------------------------------------------------------------------------- CLI


def test_cli_abstract_writes_run_record(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=2)
    code = main(["abstract", "--root", str(tmp_path), "--as-of", fmt_iso(LATER), "--off"])
    assert code == 0
    records = load_runs(config.layout)
    assert len(records) == 1
    assert records[0].status == STATUS_INSUFFICIENT


def test_cli_abstract_json_and_dry_run(tmp_path: Path) -> None:
    config = _workspace(tmp_path, n_samples=2)
    code = main(
        [
            "abstract",
            "--root",
            str(tmp_path),
            "--as-of",
            fmt_iso(LATER),
            "--off",
            "--dry-run",
            "--json",
        ]
    )
    assert code == 0
    assert not config.layout.abstract_runs_jsonl.exists()  # dry-run 不落盘


def test_cli_abstract_rejects_missing_time_when_no_samples(tmp_path: Path) -> None:
    _workspace(tmp_path, n_samples=0)
    code = main(["abstract", "--root", str(tmp_path), "--off"])
    assert code == 2  # 参数错误：时间不取运行时钟


def test_init_creates_library_and_abstract_dirs(tmp_path: Path) -> None:
    assert main(["init", "--root", str(tmp_path)]) == 0
    assert (tmp_path / "patterns" / "library.yaml").read_text(encoding="utf-8").strip() == "[]"
    assert not (tmp_path / "scope.yaml").exists()
    assert (tmp_path / "data" / "abstract").is_dir()
    assert (tmp_path / "data" / "llm_cache").is_dir()


def test_config_template_has_domains_and_abstract(tmp_path: Path) -> None:
    """init 生成的 config.yaml 必须带新节，且能被解析（防止模板与 DEFAULT_CONFIG 漂移）。"""
    assert main(["init", "--root", str(tmp_path)]) == 0
    raw = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert "domains" in raw and "abstract" in raw
    config = Config.load(tmp_path)
    assert config.domain_ids and config.abstract.cluster_min_new_projects == 6
    assert parse_iso(fmt_iso(LATER)).year == 2026
