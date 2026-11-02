# 贡献指南

本仓库的红线定义在 `CODEBUDDY.md` §4（最高 12 条 + 项目特有 8 条 + 工程类 8 条）。
**动手前先读那份**，本文件只写"怎么干活"。

## 门禁（四条，缺一不可）

```bash
pytest
ruff check .
ruff format --check .
mypy                     # strict，files = ["osslens"]
```

`mypy` 不走 `tests/`，但**不允许**用 `# type: ignore` 掩盖问题——必要时用 `cast`。

## 测试约定

- **断言必须打到真实输出结构**：JSON 字段值、报告行文本、文件字节。
  不得断言注释或说明文字（他项目踩过：脚注含 `★`，导致 `assert "★" in output` 恒真）。
- **时间驱动逻辑必须有跨天 / 跨周用例**，用 `osslens.util.FixedClock` 推进，不用 `sleep`。
- **不伪造 fixtures**：需要真实响应就真实抓取；抓不到就 `pytest.skip(reason=...)` 并写明原因。
  单元测试里构造的结构化快照只用于验证渲染/打分/时序，真实证据由 `pool add` / `analyze` 的真实运行提供。

## 提交约定

| 项 | 规则 |
|---|---|
| 粒度 | **一个 commit 一类改动**；`git add -p` 或按路径 add，**不用 `git add -A`** |
| 编号 | commit 编号 / tag 由项目负责人定 |
| 强制推 | 禁止 |
| `git clean -fd` | 禁止（会清掉未跟踪的过程材料） |
| 提交失败 | 先跑 `pre-commit run --all-files --verbose`，**不用 `--no-verify`** |
| 敏感文件 | 提交前 `git ls-files \| grep -E '\.env$\|secrets\|\.db$'` 必须为空 |

## 数据文件

`data/pool/pool.jsonl` / `data/costs/costs.jsonl` / `data/ledger/selected.jsonl` 是 **append-only 真源**：
只追加，不修改、不删除。任何删除类操作先列清单、停下等确认。

`data/featcards/` 与 `site/` 可丢弃、可重建。

## 文档

- `docs/设计方案.md` / `docs/执行手册.md` / `docs/文档维护日志.md` **只读**，由项目负责人维护。
- `docs/开发日志.md` 由开发者在每个阶段收尾追加。
