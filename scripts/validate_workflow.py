"""T7 降级校验：actionlint 不可用时的本地等价校验（不联网、不 push、不建 remote）。

actionlint 是 Go 二进制；本环境 github.com 出站超时、无 go、docker 镜像拉取被拒，
故用本脚本对 workflow 做**结构与红线**静态校验，并逐项打印 PASS/FAIL。
★ 它替代的是 actionlint 的语法/schema 检查，不替代 GitHub 的真实 run。
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/pool.yml")


def main() -> int:
    if not WORKFLOW.exists():
        print(f"FAIL 缺少 {WORKFLOW}")
        return 1
    raw = WORKFLOW.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        print(f"FAIL YAML 解析失败：{exc}")
        return 1

    # GitHub Actions 的 `on` 在 YAML 1.1 里会被解析成布尔 True，两种都接受
    triggers = doc.get("on", doc.get(True, {}))
    jobs = doc.get("jobs") or {}
    steps: list[dict] = []
    for job in jobs.values():
        steps.extend(job.get("steps") or [])
    runs = "\n".join(str(job.get("runs-on", "")) for job in jobs.values())
    # 负向检查只看**会执行的命令**，注释里提到某个命令不算违规（否则会误报）
    script_lines = [
        line
        for step in steps
        for line in str(step.get("run", "")).splitlines()
        if not line.lstrip().startswith("#")
    ]
    script = "\n".join(script_lines)

    checks: list[tuple[str, bool]] = [
        ("YAML 可解析且含 schedule 定时", bool(triggers and "schedule" in triggers)),
        ("含 workflow_dispatch 手动入口", bool(triggers and "workflow_dispatch" in triggers)),
        ("runner 固定 ubuntu-24.04", "ubuntu-24.04" in runs),
        ("未使用 ubuntu-latest", "ubuntu-latest" not in runs),
        ("声明 contents: write 权限", (doc.get("permissions") or {}).get("contents") == "write"),
        ("使用 GITHUB_TOKEN（原文，含 env 绑定）", "GITHUB_TOKEN" in raw),
        ("git pull --ff-only", "git pull --ff-only" in script),
        (
            "工作区脏则显式跳过（warning + dirty 守卫）",
            "dirty" in script and "::warning::" in script,
        ),
        (
            "按路径 git add（不用 git add -A）",
            "git add --" in script and "git add -A" not in script,
        ),
        ("禁止 git clean", "git clean" not in script),
        ("空提交防护（diff --cached --quiet）", "diff --cached --quiet" in script),
        (
            "真源路径覆盖 pool/ledger/snapshots",
            all(p in script for p in ("data/pool", "data/ledger", "data/snapshots")),
        ),
        ("只调 pool add（零 LLM，深挖不进定时）", "pool" in script and "analyze" not in script),
    ]
    failed = 0
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            failed += 1
    print(f"\n合计 {len(checks) - failed}/{len(checks)} 通过")
    if failed:
        print("★ actionlint 未安装（降级路径）：以上为静态校验，不等同于 GitHub 真实 run")
        return 1
    print("★ actionlint 未安装（降级路径）：以上为静态校验，不等同于 GitHub 真实 run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
