"""Q2 + Q7（实现轮 v1.0 T3）：paradigm_tags schema / prompt / 校验 / 缓存键 + 纯静态前端三能力。

★ 零脚本契约：所有新页面不得含 <script> / 外部资源 / CDN（与 test_l4.py 同一红线）。
★ 真源纯净：标签过滤以报告 paradigm_tags 为数据源，无标注时诚实空态，不伪造（红线 8）。
★ 覆盖：受控词表过滤 / parse+from_json+validate / prompt 含字段 / cache_key 随 schema /
  render 洞见行 / 检索页+JSON 索引 / 标签页（空态与注入填充）/ 并排对比（2–3 张、<2 空态）/
  nav 三入口 / index.md 可脱离网络 / 幂等 / --check 一致。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from osslens.config import Config, Layout
from osslens.llm import (
    PARADIGM_TAGS,
    Insight,
    InsightItem,
    Usage,
    cache_key,
    normalize_paradigm_tags,
    parse_insight,
    validate_insight,
)
from osslens.prompts import FAST_INSIGHT_SYSTEM, STRONG_INSIGHT_SYSTEM
from osslens.site import build_site, site_check, write_site
from osslens.util import fmt_iso, sha256_text, stable_json

from .conftest import write_config

AS_OF = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- paradigm_tags schema


def test_paradigm_tags_vocabulary_is_controlled_and_sorted() -> None:
    assert "深优化" in PARADIGM_TAGS and "缓存复用" in PARADIGM_TAGS
    out = normalize_paradigm_tags(["深优化", "乱造标签", "缓存复用", "深优化"])
    assert out == ("深优化", "缓存复用"), "只保留词表内值，排序去重"
    assert normalize_paradigm_tags(None) == ()


def test_parse_insight_reads_and_filters_paradigm_tags() -> None:
    content = json.dumps(
        {
            "items": [
                {"id": "t1", "chose": "a", "alternative": "b", "cost": "c", "evidence": "x.py:1"}
            ],
            "confidence": "high",
            "paradigm_tags": ["缓存复用", "表外标签", "深优化"],
        }
    )
    ins = parse_insight(content, max_tokens=4096, usage=Usage(10, 5, 0, 0, 15))
    assert ins is not None
    assert ins.paradigm_tags == ("深优化", "缓存复用")
    # to_json / from_json 往返保留
    restored = Insight.from_json(ins.to_json())
    assert restored.paradigm_tags == ins.paradigm_tags


def test_validate_insight_keeps_paradigm_tags() -> None:
    ins = Insight(
        items=(InsightItem("t1", "a", "b", "c", "x.py:1"),),
        confidence="med",
        dropped=(),
        paradigm_tags=("单体内核",),
    )
    kept = validate_insight(ins, allowed_paths={"x.py"})
    assert kept.items and kept.paradigm_tags == ("单体内核",)


def test_prompts_and_cache_key_reflect_new_schema() -> None:
    assert "paradigm_tags" in FAST_INSIGHT_SYSTEM
    assert "paradigm_tags" in STRONG_INSIGHT_SYSTEM
    # 词表约束写进 system；system 进 cache_key → 不同 schema 文本产生不同缓存键
    assert "深优化" in FAST_INSIGHT_SYSTEM
    k_old = cache_key("m", False, "old-system-without-tags", "u")
    k_new = cache_key("m", False, FAST_INSIGHT_SYSTEM, "u")
    assert k_old != k_new, "prompt/schema 变更必须使缓存键同步失效"


def test_evidence_appendix_carries_paradigm_tag_line() -> None:
    from types import SimpleNamespace

    from osslens.render import _evidence_appendix

    ins = Insight(
        items=(InsightItem("t1", "a", "b", "c", "x.py:1"),),
        confidence="high",
        dropped=(),
        paradigm_tags=("缓存复用", "深优化"),
    )
    # 附录 A 只依赖 insight / insight_reason / pattern_hits / 外部探测，无需完整 DepthDecision
    lines = _evidence_appendix(
        SimpleNamespace(
            insight=ins,
            insight_reason="",
            pattern_hits=(),
            owner="o",
            repo="r",
            external=None,
            snapshot_notes=(),
        )
    )
    text = "\n".join(lines)
    assert "- 架构范式标签：缓存复用、深优化" in text
    assert lines[0] == "## 附录 A 证据索引与未知项"
    assert "### A3. 未获得项" in text


# --------------------------------------------------------------------------- 站点三能力


def _card(repo: str, *, stars: int = 10000) -> dict:
    return {
        "identity": {
            "repo": repo,
            "commit": "a" * 40,
            "analyzed_at": fmt_iso(AS_OF),
            "channel": "classic",
        },
        "scale": {"stars": stars},
        "parallel": {"hits": {"TP": False}, "evidence": {}},
        "cache": {"hits": {"paged": False}, "evidence": {}},
        "hardware": {"vendors": [], "arch_gates": [], "kernel_langs": []},
        "governance": {"org_type": "Organization", "license": "MIT"},
    }


def _report_md(repo: str, *, tags: tuple[str, ...] = ()) -> str:
    insight = "—"
    if tags:
        insight = (
            "| id | 选择 | 放弃的替代 | 代价 | 证据 |\n|---|---|---|---|---|\n"
            "| t1 | a | b | c | `x.py:1` |\n\n"
            "- 置信度：high\n"
            f"- 架构范式标签：{'、'.join(tags)}\n"
        )
    return (
        f"# 开源项目分析 · {repo}\n\n## 运行元数据\n\n| 项 | 值 |\n|---|---|\n"
        f"| 仓库 | {repo} |\n| 分析基准时间 (as-of) | 2026-11-06T00:00:00Z |\n"
        "| **实际档位** (actual_depth) | fast |\n| 成本说明 | 本次 ¥0.0459 |\n"
        "| 单价 | deepseek-flash ¥2/M |\n\n## 体检事实（确定性，零 LLM）\n\n"
        "| 指标 | 值 |\n|---|---|\n| Star / Fork | 10,000 / 1,000 |\n\n"
        "```mermaid\ngraph TD\n  A[无]\n```\n\n## 特征卡摘要\n\n（L0）\n\n"
        f"## 洞见\n\n{insight}\n## 外部资料\n\n不可用（未索引）\n"
    )


def _workspace(tmp_path: Path, *, tags: tuple[tuple[str, ...], ...] = ((), (), ())) -> Config:
    root = tmp_path / "ws"
    layout = Layout(root)
    layout.ensure_skeleton()
    write_config(root)
    repos = ["org/one", "org/two", "org/three"]
    for i, repo in enumerate(repos):
        (layout.reports_dir / f"{repo.replace('/', '__')}__2026-11-06.md").write_text(
            _report_md(repo, tags=tags[i]), encoding="utf-8"
        )
        (layout.featcards_dir / f"{repo.replace('/', '__')}__c{i}.json").write_text(
            json.dumps(_card(repo, stars=10000 + i)), encoding="utf-8"
        )
    layout.library_patterns.write_text("[]\n", encoding="utf-8")
    return Config.load(root)


def test_three_static_pages_exist_offline_and_zero_script(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    plan = build_site(config, as_of=AS_OF)
    for name in ("search.html", "search-index.json", "tags.html", "compare.html"):
        assert name in plan.files, f"缺静态能力产物 {name}"
    for content in plan.files.values():
        assert "<script" not in content
        assert 'src="http' not in content and "cdn." not in content
    # nav 三入口
    assert 'href="search.html"' in plan.files["index.html"]
    assert 'href="tags.html"' in plan.files["index.html"]
    assert 'href="compare.html"' in plan.files["index.html"]
    # 检索：本地 JSON 索引可脱离站点阅读（仓库名 / 关键词）
    index = json.loads(plan.files["search-index.json"])
    assert [e["repo"] for e in index["entries"]] == ["org/one", "org/three", "org/two"]
    assert any("one" in e["keywords"] for e in index["entries"])
    # 并排对比：取前 3 张特征卡
    compare = plan.files["compare.html"]
    assert "org/one" in compare and "org/two" in compare and "org/three" in compare
    assert "stars" in compare


def test_tags_page_empty_state_is_honest(tmp_path: Path) -> None:
    config = _workspace(tmp_path, tags=((), (), ()))
    tags_page = build_site(config, as_of=AS_OF).files["tags.html"]
    assert "当前无 fast/strong 报告带架构范式标签" in tags_page
    assert "不伪造" in tags_page


def test_tags_page_fills_from_injected_paradigm_tags(tmp_path: Path) -> None:
    config = _workspace(tmp_path, tags=(("缓存复用",), ("深优化",), ("缓存复用", "深优化")))
    plan = build_site(config, as_of=AS_OF)
    tags_page = plan.files["tags.html"]
    assert "当前无 fast/strong" not in tags_page
    assert "共 12 个标签 / 4 次标注" in tags_page  # 词表 12 / 标注 1+1+2
    # 标签分组锚点 + 报告链接
    assert "org/one" in tags_page and "缓存复用" in tags_page
    # 表外标签不被解析（_report_paradigm_tags 只认词表）
    config2 = _workspace(tmp_path / "x", tags=(("乱造标签",), (), ()))
    page2 = build_site(config2, as_of=AS_OF).files["tags.html"]
    assert "乱造标签" not in page2


def test_compare_page_empty_state_with_fewer_than_two(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    layout = Layout(root)
    layout.ensure_skeleton()
    write_config(root)
    (layout.featcards_dir / "org__one__c.json").write_text(
        json.dumps(_card("org/one")), encoding="utf-8"
    )
    layout.library_patterns.write_text("[]\n", encoding="utf-8")
    page = build_site(Config.load(root), as_of=AS_OF).files["compare.html"]
    assert "不足 2 张" in page


def test_site_idempotent_and_check_consistent(tmp_path: Path) -> None:
    config = _workspace(tmp_path, tags=(("缓存复用",), ("深优化",), ()))
    first = build_site(config, as_of=AS_OF)
    second = build_site(config, as_of=AS_OF)
    assert sha256_text(stable_json(first.files)) == sha256_text(stable_json(second.files))
    out = tmp_path / "out-site"
    write_site(out, first.files)
    assert site_check(out, first.files) == ()
    # v3 权重是注意力预算，必须完整覆盖 6 章 + 工程维护，且总和为 100
    from osslens.render import REPORT_PROFILES

    for profile, weights in REPORT_PROFILES.items():
        assert sum(weights.values()) == 100, profile
        assert set(weights) == {"定位", "架构", "抽象", "ADR", "扩展", "经验卡", "工程维护"}
