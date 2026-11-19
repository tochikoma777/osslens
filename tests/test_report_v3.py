"""v3 报告模板（导读 + 6 章 + 附录 A/B）的质量守护。

守护点（任一回归都应让本文件变红）：
1. 头部声明阅读档位与「事实 / 判断 / 未获得」三分；
2. ADR 必须写满六字段，缺规则/边界时显式「未获得」，不许留空；
3. 经验卡必须有 rule，禁止用通用建议凑数；
4. profile 白名单与权重完整（配置层 fail-fast，渲染层权重和为 100）；
5. 架构模式扫描是确定性、去重的；
6. insight 的 rule/boundary 能穿过缓存序列化，旧缓存缺字段时退化为空。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from osslens.cli import _pattern_hits
from osslens.cli import main as cli_main
from osslens.config import (
    DEFAULT_CONFIG,
    REPORT_PROFILE_NAMES,
    Config,
    ConfigError,
)
from osslens.llm import Insight, InsightItem
from osslens.render import REPORT_PROFILES, _adr_section, _experience_section
from osslens.util import fmt_iso

from .conftest import AS_OF, seed_workspace


def test_profile_whitelist_matches_profiles() -> None:
    """配置白名单与渲染权重必须同源同名，防止只改一侧导致静默回退。"""
    assert tuple(REPORT_PROFILES) == REPORT_PROFILE_NAMES
    for weights in REPORT_PROFILES.values():
        assert sum(weights.values()) == 100


def test_config_rejects_unknown_profile(tmp_path: Path) -> None:
    seed_workspace(tmp_path / "ws")
    with pytest.raises(ConfigError):
        Config.from_mapping(tmp_path / "ws", {"report": {"profile": "no_such_profile"}})


def test_profile_is_declared_in_report_header(tmp_path: Path) -> None:
    """切换档位后，报告头部必须如实标注档位与注意力预算。"""
    root = seed_workspace(
        tmp_path / "ws", overrides={"report": {"profile": "adoption_due_diligence"}}
    )
    assert (
        cli_main(
            [
                "analyze",
                "deepseek-ai/DeepEP",
                "--root",
                str(root),
                "--no-sources",
                "--as-of",
                fmt_iso(AS_OF),
            ]
        )
        == 0
    )
    text = (root / "reports" / "deepseek-ai__DeepEP__2026-11-02.md").read_text(encoding="utf-8")
    assert "> 阅读档位：选型尽调（profile=adoption_due_diligence）" in text
    assert "工程维护 45" in text
    assert "证据约定：[事实] 确定性提取" in text


def _insight(*items: InsightItem) -> Insight:
    return Insight(items=items, confidence="high", dropped=())


def test_adr_renders_six_fields_and_marks_missing_rule() -> None:
    """ADR 六字段缺一不可；模型没给规则/边界时必须显式未获得。"""
    item = InsightItem("t1", "用 A", "用 B", "多写 200 行", "src/a.py:12")
    text = "\n".join(_adr_section(SimpleNamespace(insight=_insight(item), insight_reason="")))
    for label in (
        "**决策**",
        "**替代**",
        "**代价**",
        "**证据**",
        "**可复用规则**",
        "**边界/反模式**",
    ):
        assert label in text
    assert "`src/a.py:12`" in text
    assert "[未获得] 模型未给出可迁移规则" in text
    assert "本次仅 1 条" in text  # 不足 3 条要说明，而不是硬凑


def test_adr_without_insight_is_explicitly_unavailable() -> None:
    text = "\n".join(_adr_section(SimpleNamespace(insight=None, insight_reason="no_credentials")))
    assert "[未获得] no_credentials" in text
    assert "### ADR-" not in text


def test_experience_card_requires_rule_and_boundary() -> None:
    """有 rule 才出卡；没有 rule 时留空并说明，不用「要注重解耦」充数。"""
    no_rule = InsightItem("t1", "A", "B", "C", "src/a.py:12")
    empty = "\n".join(
        _experience_section(SimpleNamespace(insight=_insight(no_rule), owner="o", repo="r"))
    )
    assert "[未获得] 本次没有带「可迁移规则」的条目" in empty
    assert "### 经验" not in empty

    with_rule = InsightItem(
        "t2",
        "A",
        "B",
        "C",
        "src/a.py:12",
        rule="运行时编译换灵活性，代价是保留工具链",
        boundary="只适合需要 JIT 特化的内核，不适合纯 Python 服务",
    )
    text = "\n".join(
        _experience_section(SimpleNamespace(insight=_insight(with_rule), owner="o", repo="r"))
    )
    assert "### 经验 1 · 运行时编译换灵活性" in text
    assert "**适用边界**：只适合需要 JIT 特化" in text
    assert "**反模式**" in text
    assert "**如果我来做**" in text


def test_pattern_scan_is_deterministic_and_deduped() -> None:
    """模式扫描：同一 (pattern, path) 只记一次，顺序按源码行号。"""
    files = [
        (
            SimpleNamespace(path="pkg/registry.py"),
            "class Registry:\n    def register(self):\n        pass\n    def register(self):\n        pass\n",
        ),
        (SimpleNamespace(path="pkg/adapter.py"), "class Adapter:\n    pass\n"),
    ]
    first = _pattern_hits(files)
    second = _pattern_hits(files)
    assert first == second
    keys = [(pattern, path) for pattern, path, _ in first]
    assert ("register", "pkg/registry.py") in keys
    assert ("adapter", "pkg/adapter.py") in keys
    assert len(keys) == len(set(keys)), "同一文件的同一模式不得重复记录"
    assert all(pattern == pattern.lower() and "(" not in pattern for pattern, _ in keys)


def test_insight_rule_boundary_survive_serialization() -> None:
    """rule/boundary 必须能过缓存序列化；旧缓存缺字段时退化为空而不报错。"""
    item = InsightItem("t1", "A", "B", "C", "src/a.py:12", rule="R", boundary="D")
    payload = item.to_json()
    assert payload["rule"] == "R" and payload["boundary"] == "D"
    restored = Insight.from_json(
        {"items": [payload], "confidence": "high", "dropped": [], "paradigm_tags": []}
    )
    assert (restored.items[0].rule, restored.items[0].boundary) == ("R", "D")

    legacy = Insight.from_json(
        {
            "items": [
                {
                    "id": "t1",
                    "chose": "A",
                    "alternative": "B",
                    "cost": "C",
                    "evidence": "src/a.py:12",
                }
            ],
            "confidence": "high",
            "dropped": [],
            "paradigm_tags": [],
        }
    )
    assert legacy.items[0].rule == "" and legacy.items[0].boundary == ""


def test_default_config_profile_is_architecture_learning() -> None:
    assert DEFAULT_CONFIG["report"]["profile"] == "architecture_learning"
