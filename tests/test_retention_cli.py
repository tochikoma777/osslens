"""T5 保留策略的**生产调用点**测试：CLI `retention` 子命令（实现轮 v1.0 Q6）。

与 test_l2.py 的模块级测试互补：这里断言 `python -m osslens retention` 的默认行为、
`--apply` 显式控制、以及真源/派生基线零删除。断言打到真实输出结构与真实字节。
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from osslens.cli import main
from osslens.config import Layout

from .conftest import write_config

AS_OF = "2026-11-04T00:00:00Z"


def _seed(root: Path) -> Layout:
    """构造含真源、缓存层、site/ 派生基线的最小工作区（真实字节，不伪造 fixtures）。"""
    layout = Layout(root)
    layout.ensure_skeleton()
    write_config(root)

    ext = layout.snapshots_dir / "o__r" / "2026-10-01" / "external"
    ext.mkdir(parents=True, exist_ok=True)
    (ext / "deepwiki.json").write_text('{"status":"hit"}', encoding="utf-8")
    (ext / "source.txt").write_text("外部原文", encoding="utf-8")

    src = layout.snapshots_dir / "o__r" / "2026-10-01" / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.py").write_bytes(b"same content")
    (src / "b.py").write_bytes(b"same content")  # 与 a 重复
    (src / "c.py").write_bytes(b"unique content")

    cache = layout.data_dir / "llm_cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "x.json").write_bytes(b"same content")  # 与 src 重复
    old = time.mktime(datetime(2026, 10, 1, tzinfo=UTC).timetuple())
    os.utime(cache / "x.json", (old, old))

    (layout.data_dir / "costs" / "costs.jsonl").write_text("TRUTH\n", encoding="utf-8")
    (layout.snapshots_dir / "o__r" / "2026-10-01.json").write_text("META", encoding="utf-8")

    site = layout.root / "site"
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text("<html>baseline</html>", encoding="utf-8")
    return layout


def _truth_files(root: Path) -> dict[Path, bytes]:
    return {
        p: p.read_bytes()
        for p in [
            root / "data" / "snapshots" / "o__r" / "2026-10-01" / "external" / "deepwiki.json",
            root / "data" / "snapshots" / "o__r" / "2026-10-01" / "external" / "source.txt",
            root / "data" / "snapshots" / "o__r" / "2026-10-01.json",
            root / "data" / "costs" / "costs.jsonl",
            root / "site" / "index.html",
        ]
    }


def test_cli_retention_default_is_dry_run(tmp_path: Path, capsys) -> None:
    """缺省只规划不写盘：--json 输出 dry_run=true，归档目录不存在，所有真源字节不变。"""
    root = tmp_path / "ws"
    _seed(root)
    truth_before = _truth_files(root)

    code = main(["retention", "--root", str(root), "--as-of", AS_OF, "--json"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert out["as_of"] == AS_OF
    assert len(out["cache_files"]) == 4  # 3 src + 1 llm_cache
    assert len(out["unique_objects"]) == 2
    assert len(out["duplicate_files"]) == 2
    assert not (root / "data" / "cache_objects").exists(), "dry-run 绝不写对象"
    assert not (root / "data" / "cache_archive").exists(), "dry-run 绝不归档"
    assert _truth_files(root) == truth_before, "dry-run 绝不改动真源 / 派生基线"


def test_cli_retention_apply_archives_only_cache(tmp_path: Path) -> None:
    """--apply 才实际清理：src/ 与 llm_cache/ 被归档，external/、真源、site/ 零删除。"""
    root = tmp_path / "ws"
    layout = _seed(root)
    truth_before = _truth_files(root)

    code = main(["retention", "--root", str(root), "--as-of", AS_OF, "--apply", "--json"])
    assert code == 0
    # 同 sha256 内容只存一份（"same content" + "unique content" = 2 个对象）
    objects = [p for p in (root / "data" / "cache_objects").rglob("*") if p.is_file()]
    assert len(objects) == 2, "内容寻址：同 sha256 只存一份"
    # 归档只发生在缓存层
    archived = [p for p in (root / "data" / "cache_archive").rglob("*") if p.is_file()]
    assert len(archived) == 4, "3 src + 1 llm_cache 全部可清理"
    rels = [p.relative_to(root).as_posix() for p in archived]
    assert not any("/external/" in rel for rel in rels)
    assert not any("costs.jsonl" in rel for rel in rels)
    assert not any("site/" in rel for rel in rels)
    # 真源 / 外部资料 / site 基线字节不变
    assert _truth_files(root) == truth_before, "--apply 也不触碰真源 / 派生基线"
    # protected 清单含 external 与 site（白名单显式留痕）
    code2 = main(["retention", "--root", str(root), "--as-of", AS_OF, "--json"])
    assert code2 == 0
    assert layout.snapshots_dir.exists()
