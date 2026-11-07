"""L4 契约测试：静态站点 / 空态诚实 / --check / 幂等 / 零网络 / 不展示敏感。

★ 红线 #10：断言打真实输出结构；新增检查点配「故意让它失败」的反向用例。
"""

from __future__ import annotations

import contextlib
import html as html_lib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from osslens import site as site_module
from osslens.cli import main
from osslens.config import Config, Layout
from osslens.site import (
    build_site,
    empty_patterns_note,
    md_to_html,
    resolve_site_as_of,
    site_check,
    write_site,
)
from osslens.util import UsageError, fmt_iso, parse_iso, sha256_text, stable_json

from .conftest import write_config

AS_OF = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)


def _card(repo: str, *, cache: bool = False) -> dict[str, Any]:
    return {
        "identity": {
            "repo": repo,
            "commit": "a" * 40,
            "analyzed_at": fmt_iso(AS_OF),
            "channel": "classic",
        },
        "scale": {"stars": 10000},
        "parallel": {"hits": {"TP": False}, "evidence": {}},
        "cache": {
            "hits": {"paged": cache},
            "evidence": {
                "paged": [{"file": "src/cache.py", "line": 7, "snippet": "y"}] if cache else []
            },
        },
        "hardware": {"vendors": [], "arch_gates": [], "kernel_langs": []},
        "governance": {"org_type": "Organization", "license": "MIT"},
    }


def _report(name: str, repo: str) -> str:
    return f"""# 开源项目分析 · {repo}

## 运行元数据

| 项 | 值 |
|---|---|
| 仓库 | {repo} |
| 分析基准时间 (as-of) | 2026-11-06T00:00:00Z |
| **实际档位** (actual_depth) | off |
| 成本说明 | 本次 —（未调用） |
| 单价 | deepseek-flash 输入 ¥2/M（官方中文页，核对 2026-11-03） |
| 口径 | 本次分析的成本（不含开发期重复调用） |

## 体检事实（确定性，零 LLM）

| 指标 | 值 |
|---|---|
| Star / Fork | 10,000 / 1,000 |

- 丢弃：—（off 档不组装上下文）

```mermaid
graph TD
  A[无]
```

## 特征卡摘要

（L0 全档有）

## 洞见

—

## 外部资料

不可用（未索引）
"""


def _workspace(tmp_path: Path, *, with_runs: bool = True, with_library: bool = True) -> Path:
    root = tmp_path / "ws"
    layout = Layout(root)
    layout.ensure_skeleton()
    write_config(root)
    (layout.reports_dir / "org__one__2026-11-06.md").write_text(
        _report("one", "org/one"), encoding="utf-8"
    )
    (layout.reports_dir / "org__two__2026-11-06.md").write_text(
        _report("two", "org/two"), encoding="utf-8"
    )
    (layout.featcards_dir / "org__one__a.json").write_text(
        json.dumps(_card("org/one", cache=True)), encoding="utf-8"
    )
    (layout.featcards_dir / "org__two__b.json").write_text(
        json.dumps(_card("org/two")), encoding="utf-8"
    )
    if with_library:
        layout.library_patterns.write_text("[]\n", encoding="utf-8")
    (layout.costs_jsonl).write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "call",
                        "repo": "org/one",
                        "depth": "fast",
                        "model": "deepseek-flash",
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "estimated_cost": 0.001,
                        "source": "api",
                        "as_of": fmt_iso(AS_OF),
                        "run_id": "r1",
                        "requested_depth": "fast",
                        "actual_depth": "fast",
                        "reason": "baseline",
                        "purpose": "fast_insight",
                    },
                    sort_keys=True,
                )
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if with_runs:
        layout.abstract_runs_jsonl.write_text(
            json.dumps(
                {
                    "run_id": "3f6e4c82e3b95f22",
                    "type": "cluster-abstraction",
                    "cluster": "inference",
                    "trigger": "新增样本 5 (>= 6)",
                    "input_projects": ["org/one"],
                    "input_patterns": [],
                    "ops": [],
                    "llm_calls": 0,
                    "created_at": fmt_iso(AS_OF),
                    "status": "insufficient_samples",
                    "self_check": {
                        "q1_has_drilldown_evidence": False,
                        "q2_new_counterexamples": 0,
                        "q3_has_cross_domain_evidence": False,
                        "q4_manual_review_target": "org/one",
                        "warnings": ["无反例"],
                    },
                    "warnings": ["样本 5 < 6"],
                    "produced_patterns": [],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return root


def _build(root: Path, out: Path) -> dict[str, str]:
    config = Config.load(root)
    plan = build_site(config, as_of=AS_OF)
    write_site(out, plan.files)
    return plan.files


# --------------------------------------------------------------------------- T1/T2/T3 四块呈现


def test_site_builds_full_static_site(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    out = tmp_path / "site"
    files = _build(root, out)
    for name in (
        "index.md",
        "index.html",
        "reports.html",
        "featcards.html",
        "patterns.html",
        "costs.html",
        "runs.html",
    ):
        assert name in files, f"缺区块 {name}"
        assert (out / name).read_text(encoding="utf-8") == files[name]
    assert len([key for key in files if key.startswith("report-")]) == 2
    for name, content in files.items():
        assert "<script" not in content, "站点不得引入脚本（无外部 JS/CDN）"
        assert 'src="http' not in content and "@import" not in content, "不得加载外部资源"
        assert "cdn." not in content, "不得依赖 CDN"
        if name.endswith(".html"):
            assert "<!doctype html>" in content


def test_index_md_is_standalone_readable(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    files = _build(root, tmp_path / "site")
    index = files["index.md"]
    for heading in ("# osslens 静态站点索引", "## 页面", "## 项目清单", "## 特征卡", "## 规律库"):
        assert heading in index
    assert "org/one" in index and "org/two" in index
    assert index.index("org/one") < index.index("org/two")  # 故意让它失败：未排序
    assert "](../reports/" in index  # 相对链接，可脱离站点阅读
    assert "site/" not in index and str(tmp_path) not in index  # 无绝对路径


def test_report_five_sections_preserved_in_order(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    files = _build(root, tmp_path / "site")
    page = next(value for key, value in files.items() if key == "report-org__one__2026-11-06.html")
    positions = [page.index(name) for name in site_module.REPORT_SECTIONS]
    assert positions == sorted(positions)  # 故意让它失败：五区块顺序被打乱
    assert len(set(positions)) == len(site_module.REPORT_SECTIONS)
    assert "<table>" in page and "<pre><code" in page  # 表格 / Mermaid 代码块都在
    assert "graph TD" in page


def test_md_to_html_renders_structures() -> None:
    html = md_to_html("## 标题\n\n| A | B |\n|---|---|\n| 1 | **粗** |\n\n- 项\n\n`code`")
    assert "<h2>标题</h2>" in html
    assert "<table>" in html and "<strong>粗</strong>" in html
    assert "<ul><li>项</li></ul>" in html
    assert "<code>code</code>" in html
    assert "<script" not in html


def test_featcard_evidence_file_line_rendered(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    files = _build(root, tmp_path / "site")
    assert "src/cache.py:7" in files["featcards.html"]  # 来自 code_evidence_from_card
    assert "org/one" in files["featcards.html"]


def test_costs_block_has_d10_wording_and_price_source(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    files = _build(root, tmp_path / "site")
    page = files["costs.html"]
    assert "本次分析的成本" in page  # D10 口径
    assert "全局台账" in page
    assert "单价只来自 config.yaml" in page
    assert "核对 2026-11-03" in page  # 单价来源与核对日期（摘自报告，不做价格复核）
    assert "本阶段不做价格复核" in page


# --------------------------------------------------------------------------- T4 空态诚实


def test_empty_patterns_state_is_honest(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    files = _build(root, tmp_path / "site")
    page = html_lib.unescape(files["patterns.html"])  # 按浏览器渲染后的文本断言
    assert "规律库尚无条目" in page
    assert "首次真实抽象未触发" in page
    assert "inference 簇 5 < 6" in page
    assert "示例" not in page  # 故意让它失败：不得生成示例条目
    assert "P-001" not in page
    # 空态必须出现在索引与首页，不能隐藏该块
    assert "规律库尚无条目" in files["index.md"]
    assert "规律库尚无条目" in html_lib.unescape(files["index.html"])


def test_empty_note_derives_numbers_from_config_and_runs(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config = Config.load(root)
    runs = [{"status": "insufficient_samples", "cluster": "agent", "trigger": "新增样本 2 (>= 9)"}]
    note = empty_patterns_note(config, runs)
    assert "agent 簇 2 < 6" in note  # 阈值来自 config，不是硬编码 6 以外的数
    assert empty_patterns_note(config, []) != ""  # 无 run 也不伪造


def test_insufficient_samples_visible_in_runs_page(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    files = _build(root, tmp_path / "site")
    page = html_lib.unescape(files["runs.html"])
    assert "insufficient_samples" in page
    assert "3f6e4c82e3b95f22" in page
    assert "样本 5 < 6" in page
    assert "首次真实抽象未触发" in page


def test_nonempty_library_is_rendered(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    layout = Layout(root)
    entry = {
        "id": "P-001",
        "level": "L2",
        "cluster": "inference",
        "statement": "前缀复用",
        "tags": ["cache-reuse"],
        "applicability": ["前缀重叠高"],
        "evidence": [
            {"repo": "org/one", "kind": "正例", "path": "src/cache.py:7", "commit": "", "note": ""}
        ],
        "counterexamples": [
            {"repo": "org/two", "kind": "反例", "path": "", "commit": "", "note": ""}
        ],
        "confidence": "中",
        "falsification": "x",
        "revision": 1,
        "status": "active",
        "cross_domains": [],
        "boundaries": [],
        "anti_patterns": [],
        "drilldown": [],
        "control_group": [],
        "claim_kind": "",
        "source": "real",
        "aliases": [],
        "soft_labels": [],
    }
    layout.library_patterns.write_text(yaml.safe_dump([entry]), encoding="utf-8")
    files = _build(root, tmp_path / "site")
    assert "P-001" in files["patterns.html"]
    assert "前缀复用" in files["patterns.html"]
    assert "规律库尚无条目" not in files["patterns.html"]  # 故意让它失败：真有条目却显示空态


# --------------------------------------------------------------------------- T6 --check


def test_site_check_reports_diff_without_writing(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    out = tmp_path / "site"
    config = Config.load(root)
    plan = build_site(config, as_of=AS_OF)
    diffs = site_check(out, plan.files)
    assert diffs and all("缺少" in item for item in diffs)
    assert not out.exists()  # 故意让它失败：--check 写盘了

    write_site(out, plan.files)
    assert site_check(out, plan.files) == ()

    (out / "index.md").write_text("被篡改", encoding="utf-8")
    diffs = site_check(out, plan.files)
    assert any(item == "内容不一致 index.md" for item in diffs)

    (out / "extra.html").write_text("x", encoding="utf-8")
    assert any(item == "多余 extra.html" for item in site_check(out, plan.files))


def test_cli_check_exit_zero_and_no_write(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    out = tmp_path / "site"
    code = main(
        ["site", "--root", str(root), "--out", str(out), "--check", "--as-of", fmt_iso(AS_OF)]
    )
    assert code == 0
    assert not out.exists()  # 只比对不写盘

    assert main(["site", "--root", str(root), "--out", str(out), "--as-of", fmt_iso(AS_OF)]) == 0
    assert (
        main(["site", "--root", str(root), "--out", str(out), "--check", "--as-of", fmt_iso(AS_OF)])
        == 0
    )


def test_cli_invalid_as_of_is_usage_error(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    assert main(["site", "--root", str(root), "--as-of", "not-a-date"]) == 2
    with pytest.raises(UsageError, match="as-of"):
        resolve_site_as_of(Layout(root), "not-a-date")


def test_site_as_of_derived_from_truth_not_clock(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    first = resolve_site_as_of(Layout(root), None)
    second = resolve_site_as_of(Layout(root), None)
    assert first == second == AS_OF  # 来自特征卡 analyzed_at / 报告文件名，不取运行时钟
    assert parse_iso(fmt_iso(first)).year == 2026


# --------------------------------------------------------------------------- T7 幂等


def test_site_idempotent_same_as_of(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config = Config.load(root)
    first = build_site(config, as_of=AS_OF)
    second = build_site(config, as_of=AS_OF)
    assert sha256_text(stable_json(first.files)) == sha256_text(stable_json(second.files))
    # 不同 as-of 允许 as-of 文本不同，但不得引入任何"运行时"差异变量
    third = build_site(config, as_of=datetime(2026, 12, 1, tzinfo=UTC))
    assert third.as_of == "2026-12-01T00:00:00Z"
    assert third.report_count == first.report_count and third.pattern_count == first.pattern_count
    for content in first.files.values():
        assert str(tmp_path) not in content, "产物含绝对路径"
        assert "generated_at" not in content and "生成时间" not in content
    source = Path(site_module.__file__).read_text(encoding="utf-8")
    assert "datetime.now" not in source and "SystemClock" not in source
    assert "time.time" not in source


def test_write_site_is_idempotent_on_disk(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    out = tmp_path / "site"
    _build(root, out)
    before = {path.name: sha256_text(path.read_text(encoding="utf-8")) for path in out.iterdir()}
    _build(root, out)
    after = {path.name: sha256_text(path.read_text(encoding="utf-8")) for path in out.iterdir()}
    assert before == after  # 故意让它失败：二次写盘产生字节漂移


def test_truth_sources_unchanged_by_site(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    layout = Layout(root)
    tracked = [
        layout.reports_dir / "org__one__2026-11-06.md",
        layout.featcards_dir / "org__one__a.json",
        layout.library_patterns,
        layout.costs_jsonl,
        layout.abstract_runs_jsonl,
    ]
    before = [path.read_bytes() for path in tracked]
    out = tmp_path / "site"
    _build(root, out)
    site_check(out, build_site(Config.load(root), as_of=AS_OF).files)
    assert [path.read_bytes() for path in tracked] == before  # 真源只读


# --------------------------------------------------------------------------- T5/T8 零网络 / 不展示敏感


def test_site_zero_network_transport_interception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """传输层拦截：site 与 site --check 两条路径都不得有真实外发请求。"""
    root = _workspace(tmp_path)
    out = tmp_path / "site"
    egress: list[str] = []
    original = httpx.HTTPTransport.handle_request

    def spy(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        egress.append(str(request.url))
        return original(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", spy)
    assert main(["site", "--root", str(root), "--out", str(out), "--as-of", fmt_iso(AS_OF)]) == 0
    assert (
        main(["site", "--root", str(root), "--out", str(out), "--check", "--as-of", fmt_iso(AS_OF)])
        == 0
    )
    assert egress == [], f"site 检测到真实外发请求：{egress}"
    # 反向用例：证明 spy 本身有效（不是恒真断言）。
    # 故意发一个必然失败的请求：即使连接失败，spy 也已在调用 original 前记录 URL。
    with httpx.Client(timeout=1.0) as client, contextlib.suppress(httpx.HTTPError):
        client.get("http://127.0.0.1:1/l4-probe")
    assert egress, "spy 失效：故意发出的请求未被记录"


def test_site_module_has_no_endpoint_literals_and_no_http_import() -> None:
    source = Path(site_module.__file__).read_text(encoding="utf-8")
    for marker in (
        "chat/completions",
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage",
        "import httpx",
        "HttpClient",
        "urlopen",
    ):
        assert marker not in source, f"site.py 出现 {marker}"
    # 现有全局守卫不应因新模块而放宽
    import osslens

    package = Path(osslens.__file__).parent
    for path in sorted(package.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in ("chat/completions", "api.openai.com", "api.anthropic.com"):
            if path.name == "llm.py" and marker == "chat/completions":
                continue
            assert marker not in text, f"{path.name} 出现端点字面量 {marker}"


def test_site_does_not_render_secrets_or_ref_docs(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / ".env").write_text(
        "OSSLENS_LLM_API_KEY='sk-THISISANOTREALKEY123456'\n", encoding="utf-8"
    )
    (root / "docs" / "ref").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "ref" / "经验库-全量.md").write_text(
        "SHOULD_NOT_APPEAR_IN_SITE", encoding="utf-8"
    )
    files = _build(root, tmp_path / "site")
    blob = "\n".join(files.values())
    assert ".env" not in blob
    assert "sk-THISISANOTREALKEY" not in blob
    assert "SHOULD_NOT_APPEAR_IN_SITE" not in blob
    assert "docs/ref" not in blob
    assert "sk-" not in blob  # 站点不渲染任何 key 形态字符串
