"""D31 反向用例：workflow 的 ``git add`` pathspec 必须在 clean tree 下可用。

背景：``data/ledger`` 是 Git 不跟踪的空目录（HEAD 中无 tracked 文件）。
本地因 ``python -m osslens init`` 调 ``ensure_skeleton()`` 留下空目录，
``git add -- data/ledger`` 不报错；CI fresh checkout 不物化空目录，
同一命令会 ``fatal: pathspec 'data/ledger' did not match any files``。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pool.yml"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="需要 git 可执行文件")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _workflow_add_pathspecs() -> list[str]:
    """从 workflow 解析 ``git add --`` 的 pathspec 集合（与实际文件保持同步）。"""
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("git add --"):
            return stripped.removeprefix("git add --").split()
    raise AssertionError("workflow 中未找到 `git add --` 行")


def _clean_tree(tmp_path: Path) -> Path:
    """模拟 fresh checkout：只物化有 tracked 文件的目录，不含 data/ledger。"""
    root = tmp_path / "repo"
    root.mkdir()
    init = _git(["init", "-q"], root)
    assert init.returncode == 0, init.stderr
    (root / "data" / "pool").mkdir(parents=True)
    (root / "data" / "pool" / "pool.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "data" / "snapshots" / "x").mkdir(parents=True)
    (root / "data" / "snapshots" / "x" / "snapshot.json").write_text("{}\n", encoding="utf-8")
    return root


def test_legacy_ledger_pathspec_fails_on_clean_tree(tmp_path: Path) -> None:
    """回归证明：旧 pathspec（含 data/ledger）在 clean tree 上必然 fatal。"""
    root = _clean_tree(tmp_path)
    result = _git(["add", "--", "data/pool", "data/ledger", "data/snapshots"], root)
    assert result.returncode != 0
    assert "pathspec 'data/ledger'" in result.stderr


def test_workflow_add_pathspecs_succeed_on_clean_tree(tmp_path: Path) -> None:
    """守卫：当前 workflow 的 pathspec 在 clean tree 上必须 exit 0。"""
    root = _clean_tree(tmp_path)
    pathspecs = _workflow_add_pathspecs()
    assert "data/ledger" not in pathspecs, (
        "data/ledger 当前无写入方，不应在 pathspec；接线时须同步改测试与 workflow"
    )
    result = _git(["add", "--", *pathspecs], root)
    assert result.returncode == 0, result.stderr


def test_pool_workflow_archives_old_snapshots_under_dirty_guard() -> None:
    """快照归档步骤必须在 dirty 守卫之后、且只动 snapshots（--snapshots-only）。"""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["build-pool"]["steps"]
    targets = [step for step in steps if "snapshots-only" in str(step.get("run", ""))]
    assert len(targets) == 1, "应当恰有一个 --snapshots-only 步骤"
    step = targets[0]
    assert "--apply" in step["run"]
    assert step.get("if") == "steps.guard.outputs.dirty == 'false'", "归档须在 dirty 守卫之后"
