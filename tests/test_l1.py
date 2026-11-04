"""L1 契约测试：外部工具 fail-closed、证据、依赖图、预算/M7 闸门、LLM 阶梯。

★ 两条外部工具用例使用 `docs/ref/` 里的**真实抓取片段**，并断言该片段仍存在于素材原文；
素材缺失则 `skip`，**不伪造 fixtures**（红线 #28）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from osslens.cli import main
from osslens.collect import SourceBundle, SourceFile, judge_external
from osslens.config import Config, Layout
from osslens.featcard import build_featcard
from osslens.llm import LlmClient, Usage, parse_insight, validate_insight
from osslens.pool import observe, threshold_flags
from osslens.util import FixedClock, sha256_bytes

from .conftest import AS_OF, make_snapshot, read_jsonl_file, seed_workspace, write_config

REF = Path(__file__).resolve().parents[1] / "docs" / "ref"
AGENT_REF = REF / "外部工具命中率实测_Agent训练组.md"
INFRA_REF = REF / "外部工具命中率实测_推理Infra组.md"


def _quote(path: Path, quote: str) -> str:
    if not path.exists():
        pytest.skip(f"素材不存在：{path}")
    text = path.read_text(encoding="utf-8")
    if quote not in text:
        pytest.skip(f"素材中未找到引用片段（已变更？）：{quote[:40]}")
    return quote


# --------------------------------------------------------------------------- 外部工具


def test_template_page_is_a_miss() -> None:
    """OpenLake 案例：HTTP 200 + 有仓库名，但正文零专属路径 → 必须判 miss。"""
    quote = _quote(AGENT_REF, "Index your code with Devin")
    html = (
        "<html><body><h1>openlake-project/OpenLake</h1>"
        f"<div>{quote}</div><button>Share</button></body></html>"
    )
    status, found = judge_external(
        html,
        repo_paths=["src/engine/mod.rs", "docs/architecture.md", "crates/openlake/Cargo.toml"],
        min_paths=3,
    )
    assert status == "miss"
    assert found == 0


def test_real_content_is_a_hit() -> None:
    """SkillSpector 案例：正文列出真实子系统路径 → 必须判 hit。"""
    quote = _quote(
        AGENT_REF,
        "Orchestration skillspector/core/graph.py",
    )
    paths = [
        "skillspector/core/graph.py",
        "skillspector/nodes/analyzers/",
        "skillspector/cli/main.py",
    ]
    html = f"<html><body><p>{quote}</p><p>{paths[1]}</p><p>{paths[2]}</p></body></html>"
    status, found = judge_external(html, repo_paths=paths, min_paths=3)
    assert status == "hit"
    assert found == 3


def test_external_probe_is_cached_and_fail_closed(tmp_path: Path) -> None:
    """同一 as-of 复用判定结果，重跑不改变报告字节。"""
    root = seed_workspace(tmp_path / "ws")
    write_config(root, {"external": {"deepwiki_enabled": False}})
    args = [
        "analyze",
        "deepseek-ai/DeepEP",
        "--root",
        str(root),
        "--as-of",
        "2026-11-02T00:00:00Z",
    ]
    assert main(args) == 0
    report = root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md"
    first = report.read_bytes()
    assert main(args) == 0
    assert report.read_bytes() == first
    assert "结论：未获得" in first.decode("utf-8")


# --------------------------------------------------------------------------- 证据与依赖图


def _bundle(tmp_path: Path, files: dict[str, str]) -> SourceBundle:
    root = tmp_path / "src"
    items = []
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        raw = text.encode("utf-8")
        items.append(SourceFile(path=path, sha256=sha256_bytes(raw), size=len(raw)))
    return SourceBundle(commit="c" * 40, tarball_sha256="t" * 64, files=tuple(items), root=root)


def test_evidence_comes_from_real_lines(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    bundle = _bundle(
        tmp_path,
        {
            "pkg/buffer.py": "import os\n# expert parallel dispatch\ndef f():\n    pass\n",
            "pkg/kernel.cu": "// radix tree cache\n__global__ void k() {}\n",
        },
    )
    card = build_featcard(
        make_snapshot(), as_of=AS_OF, channel="classic", config=config, sources=bundle
    )
    assert card["parallel"]["hits"]["EP"] is True
    evidence = card["parallel"]["evidence"]["EP"][0]
    assert evidence["file"] == "pkg/buffer.py"
    assert evidence["line"] == 2
    assert "expert parallel" in evidence["snippet"]
    assert card["cache"]["hits"]["radix"] is True
    # 没有证据的轴必须 false
    assert card["parallel"]["hits"]["TP"] is False
    assert "TP" not in card["parallel"]["evidence"]


def test_dep_graph_edges_and_mermaid_sorted(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    bundle = _bundle(
        tmp_path,
        {
            "pkg/__init__.py": "from .buffer import Buffer\n",
            "pkg/buffer.py": "from pkg.kernel import launch\n",
            "pkg/kernel.py": "import os\n",
            "csrc/deep_ep.cuh": "#pragma once\n",
            "csrc/main.cu": '#include "deep_ep.cuh"\n',
        },
    )
    card = build_featcard(
        make_snapshot(), as_of=AS_OF, channel="classic", config=config, sources=bundle
    )
    graph = card["deps"]["graph"]
    assert ["pkg/buffer", "pkg/kernel"] in graph["edges"]
    assert ["pkg", "pkg/buffer"] in graph["edges"]
    assert ["csrc/main", "csrc/deep_ep"] in graph["edges"]
    assert graph["edges"] == sorted(graph["edges"]), "边必须排序"
    assert card["deps"]["internal_edge_count"] == len(graph["edges"])


def test_mermaid_empty_state_is_explicit() -> None:
    from osslens.featcard import depgraph_mermaid

    assert depgraph_mermaid({"nodes": [], "edges": []}) == (
        "graph TD\n  A[无可提取的内部模块依赖边]"
    )


# --------------------------------------------------------------------------- 闸门


def test_budget_gate_blocks_and_double_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D6-4：预算闸门故意触发的反向测试——blocked + 报告 + 台账三处可见。"""
    monkeypatch.setenv("OSSLENS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OSSLENS_LLM_BASE_URL", "https://llm.invalid")
    root = seed_workspace(
        tmp_path / "ws",
        overrides={"depth": {"budget": {"per_run_prompt_tokens": 1}}},
    )
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "fast",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0, "预算拦截是正常完成，退出码必须为 0"
    text = (root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md").read_text(encoding="utf-8")
    assert "budget_blocked" in text
    assert "| **实际档位** (actual_depth) | off（降级" in text
    records = read_jsonl_file(root / "data" / "costs" / "costs.jsonl")
    assert any(
        row["event"] == "blocked" and row["reason"] == "budget_blocked" for row in records
    ), "预算拦截应记 blocked 事件（不是普通 downgrade）"


def test_max_calls_per_run_blocks_without_losing_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M7：超调用上限硬停、退出码 0、候选仍在池中（M5）。"""
    root = seed_workspace(
        tmp_path / "ws", overrides={"depth": {"budget": {"max_calls_per_run": 0}}}
    )
    monkeypatch.setenv("OSSLENS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OSSLENS_LLM_BASE_URL", "https://llm.invalid")
    observe(Layout(root), make_snapshot(), channel="hot", clock=FixedClock(AS_OF))
    code = main(
        [
            "analyze",
            "deepseek-ai/DeepEP",
            "--root",
            str(root),
            "--no-sources",
            "--depth",
            "fast",
            "--as-of",
            "2026-11-02T00:00:00Z",
        ]
    )
    assert code == 0
    text = (root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md").read_text(encoding="utf-8")
    assert "max_calls_per_run" in text
    assert "## 洞见" in text
    records = read_jsonl_file(root / "data" / "costs" / "costs.jsonl")
    assert any(row["event"] == "blocked" for row in records)
    assert read_jsonl_file(root / "data" / "pool" / "pool.jsonl"), "候选不得因拦截被丢弃"


# --------------------------------------------------------------------------- 配置与池


def test_legacy_model_env_is_ignored(tmp_path: Path) -> None:
    """旧 config 的 llm.model_env 不应导致未知键报错（D6-1 迁移）。"""
    root = tmp_path / "ws"
    root.mkdir()
    (root / "config.yaml").write_text(
        "llm:\n  model_env: OSSLENS_LLM_MODEL\n  models:\n    fast: deepseek-flash\n",
        encoding="utf-8",
    )
    config = Config.load(root)
    assert config.model_for("fast") == "deepseek-flash"
    assert config.model_for("strong") == "deepseek-v4-pro"


def test_pool_threshold_flags_but_still_ingests(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    flags = threshold_flags(
        config,
        [],
        repo="a/b",
        channel="classic",
        stars=10,
        created_at="2026-01-01T00:00:00Z",
        observed_at=AS_OF,
    )
    assert any("below_classic_min_stars" in flag for flag in flags)
    watch_flags = threshold_flags(
        config,
        [],
        repo="a/b",
        channel="watchlist",
        stars=10,
        created_at="",
        observed_at=AS_OF,
    )
    assert watch_flags == (), "watchlist 豁免门槛（意图层）"


# --------------------------------------------------------------------------- LLM 客户端


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> LlmClient:
    from osslens.config import LlmCredentials

    return LlmClient(
        LlmCredentials(api_key="k", base_url="https://llm.test"),
        model="deepseek-flash",
        thinking=False,
        timeout_seconds=5,
        max_retries=0,
        sleep=lambda _seconds: None,
        transport=httpx.MockTransport(handler),
    )


def test_deepseek_ladder_skips_json_schema() -> None:
    client = _client(lambda request: httpx.Response(200, json={}))
    assert client.formats()[0] == "json_object"


def test_parse_insight_rejects_empty_and_truncated() -> None:
    usage = Usage(10, 0, 0, 10, 10)
    assert parse_insight("", max_tokens=4096, usage=usage) is None
    truncated = Usage(10, 4096, 0, 10, 4106)
    payload = '{"items":[{"id":"t1","chose":"a","alternative":"b","cost":"c","evidence":"f:1"}]}'
    assert parse_insight(payload, max_tokens=4096, usage=truncated) is None


def test_insight_evidence_must_resolve() -> None:
    from osslens.llm import Insight, InsightItem

    insight = Insight(
        items=(
            InsightItem("t1", "a", "b", "c", "pkg/x.py:10"),
            InsightItem("t2", "a", "b", "c", "other/y.py:3"),
            InsightItem("t3", "a", "b", "c", "no-line"),
        ),
        confidence="med",
        dropped=(),
    )
    result = validate_insight(insight, allowed_paths={"pkg/x.py"})
    assert [item.id for item in result.items] == ["t1"]
    assert len(result.dropped) == 2


def test_every_true_has_evidence(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    config = Config.from_mapping(root)
    bundle = _bundle(
        tmp_path,
        {"pkg/a.py": "tensor parallel helper\nexpert parallel dispatch\nradix lookup\n"},
    )
    card = build_featcard(
        make_snapshot(), as_of=AS_OF, channel="classic", config=config, sources=bundle
    )
    for section in ("parallel", "cache"):
        for axis, flag in card[section]["hits"].items():
            if flag:
                assert card[section]["evidence"].get(axis), f"{axis}=true 却没有 evidence"
            else:
                assert axis not in card[section]["evidence"], f"{axis}=false 却有 evidence"


def test_real_featcard_evidence_points_to_real_lines() -> None:
    """真实产物自检：证据必须能定位到源码切片的对应行（没有产物则 skip）。"""
    repo_root = Path(__file__).resolve().parents[1]
    cards = sorted((repo_root / "data" / "featcards").glob("deepseek-ai__DeepEP__*.json"))
    if not cards:
        pytest.skip("尚无真实特征卡产物")
    card = json.loads(cards[-1].read_text(encoding="utf-8"))
    commit = card["identity"]["commit"]
    src_root = repo_root / "data" / "snapshots" / "deepseek-ai__DeepEP"
    candidates = [path for path in src_root.glob("*/src") if path.is_dir()]
    if not candidates:
        pytest.skip("尚无真实源码切片")
    root = candidates[0]
    checked = 0
    for section in ("parallel", "cache"):
        for axis, items in card[section]["evidence"].items():
            for item in items:
                target = root / item["file"]
                if not target.exists():
                    pytest.skip(f"切片中缺少 {item['file']}（采集参数已变？）")
                lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
                assert 1 <= item["line"] <= len(lines)
                assert item["snippet"] in lines[item["line"] - 1], (
                    f"{axis} 证据与源文件不符：{item['file']}:{item['line']}"
                )
                checked += 1
    assert checked > 0, f"commit {commit} 的特征卡没有任何证据"


def test_mermaid_in_report_and_rerun_identical(tmp_path: Path) -> None:
    """预置源码切片（模拟已缓存）→ 报告含排序后的 Mermaid，两次运行字节一致。"""
    root = seed_workspace(tmp_path / "ws")
    src = root / "data" / "snapshots" / "deepseek-ai__DeepEP" / "2026-11-02" / "src"
    files = {
        "pkg/__init__.py": "from .buffer import Buffer\n",
        "pkg/buffer.py": "from pkg.kernel import launch\n",
        "pkg/kernel.py": "import os\n",
    }
    entries = []
    for path, text in files.items():
        target = src / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        raw = text.encode("utf-8")
        entries.append({"path": path, "sha256": sha256_bytes(raw), "size": len(raw)})
    (src / "manifest.json").write_text(
        json.dumps(
            {"commit": "a" * 40, "tarball_sha256": "b" * 64, "files": entries},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    args = [
        "analyze",
        "deepseek-ai/DeepEP",
        "--root",
        str(root),
        "--as-of",
        "2026-11-02T00:00:00Z",
    ]
    assert main(args) == 0
    report = root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md"
    first = report.read_text(encoding="utf-8")
    block = first.split("```mermaid", 1)[1].split("```", 1)[0]
    assert "graph TD" in block
    edges = [line.strip() for line in block.splitlines() if "-->" in line]
    assert edges == sorted(edges), "Mermaid 边必须排序"
    assert "pkg_buffer --> pkg_kernel" in block

    assert main(args) == 0
    assert report.read_text(encoding="utf-8") == first


def test_cost_command_reports_cache_and_purpose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from osslens.depth import CostEvent, record_event

    root = seed_workspace(tmp_path / "ws")
    config = Config.load(root)
    record_event(
        config.layout,
        CostEvent(
            event="call",
            repo="deepseek-ai/DeepEP",
            depth="fast",
            model="deepseek-flash",
            prompt_tokens=1000,
            completion_tokens=100,
            estimated_cost=0.0028,
            source="api",
            as_of="2026-11-02T09:00:00Z",
            run_id="r1",
            requested_depth="fast",
            actual_depth="fast",
            reason="",
            cache_hit_tokens=800,
            cache_miss_tokens=200,
            purpose="fast_insight",
        ),
    )
    assert main(["cost", "--root", str(root), "--as-of", "2026-11-02T00:00:00Z"]) == 0
    output = capsys.readouterr().out
    assert "缓存命中 800" in output
    assert "按用途 fast_insight：1 次" in output


# --------------------------------------------------------------------------- LLM 客户端细节


def _ok_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_llm_success_parses_usage() -> None:
    body = {
        "model": "deepseek-flash",
        "choices": [
            {
                "message": {
                    "content": '{"items":[{"id":"t1","chose":"a","alternative":"b",'
                    '"cost":"c","evidence":"pkg/x.py:1"}],"confidence":"low"}'
                }
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 5,
            "total_tokens": 105,
            "prompt_cache_hit_tokens": 40,
            "prompt_cache_miss_tokens": 60,
        },
    }
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _ok_response(body)

    client = _client(handler)
    outcome = client.chat_json("sys", "user")
    assert seen[0]["response_format"] == {"type": "json_object"}, "DeepSeek 首级必须是 json_object"
    assert seen[0]["thinking"] == {"type": "disabled"}, "fast 档必须显式关 thinking"
    assert outcome.usage.cache_hit_tokens == 40
    assert outcome.usage.cache_miss_tokens == 60


def test_llm_auth_error_does_not_retry() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, text="bad key")

    outcome = _client(handler).chat_json("sys", "user")
    assert outcome.status == "error"
    assert len(calls) == 1, "401 不得重试"
    assert "401" in outcome.reason


def test_llm_retries_on_429_then_succeeds() -> None:
    seq = [
        httpx.Response(429, text="slow down"),
        httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"items":[{"id":"t1","chose":"a","alternative":"b","cost":"c","evidence":"x.py:1"}]}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return seq.pop(0)

    from osslens.config import LlmCredentials

    client = LlmClient(
        LlmCredentials(api_key="k", base_url="https://llm.test"),
        model="deepseek-flash",
        thinking=False,
        timeout_seconds=5,
        max_retries=1,
        sleep=lambda _seconds: None,
        transport=httpx.MockTransport(handler),
    )
    outcome = client.chat_json("sys", "user")
    assert outcome.status == "ok"
    assert outcome.insight is not None and outcome.insight.items[0].id == "t1"


def test_llm_result_cache_roundtrip(tmp_path: Path) -> None:
    from osslens.llm import Insight, InsightItem, LlmOutcome, load_cached, store_cache

    target = tmp_path / "cache.json"
    outcome = LlmOutcome(
        status="ok",
        reason="",
        insight=Insight((InsightItem("t1", "a", "b", "c", "x.py:1"),), "med", ()),
        usage=Usage(10, 2, 4, 6, 12),
        model="deepseek-flash",
        format_used="json_object",
        calls=1,
    )
    store_cache(target, outcome)
    restored = load_cached(target)
    assert restored is not None
    assert restored.status == "cache_hit"
    assert restored.usage.prompt_tokens == 10
    assert restored.insight is not None and restored.insight.items[0].evidence == "x.py:1"


def test_context_drops_sources_when_over_budget() -> None:
    from osslens.llm import assemble_context

    context = assemble_context(
        card_json="{}",
        readme="r" * 400,
        source_files=[(f"pkg/f{i}.py", "x" * 4000) for i in range(5)],
        budget_tokens=300,
    )
    names = [block.name for block in context.blocks]
    assert "featcard" in names
    assert not any(name.startswith("source_files") for name in names)
    assert context.dropped


# --------------------------------------------------------------------------- 外部探测（fail-closed）


class _FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        return self._response


def test_probe_blocked_page_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from osslens import collect as collect_module
    from osslens.collect import probe_external

    root = seed_workspace(
        tmp_path / "ws",
        overrides={"external": {"deepwiki_enabled": True, "deepwiki_transport": "html"}},
    )
    config = Config.load(root)
    monkeypatch.setattr(
        collect_module.httpx,
        "Client",
        lambda **_kwargs: _FakeClient(_FakeResponse(429, "Vercel Security Checkpoint")),
    )
    probe = probe_external(
        config,
        config.layout,
        "deepseek-ai",
        "DeepEP",
        as_of=AS_OF,
        clock=FixedClock(AS_OF),
        repo_paths=["deep_ep/buffer.py"],
    )
    assert probe.status == "blocked"
    assert "checkpoint" in probe.reason.lower()
    meta = (
        config.layout.snapshot_dir("deepseek-ai", "DeepEP")
        / "2026-11-02"
        / "external"
        / "deepwiki.json"
    )
    assert meta.exists(), "判定元数据必须落盘（四元组）"
