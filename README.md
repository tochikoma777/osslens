# osslens

> 低成本、可长期运行的开源项目深度分析系统。
> 建候选池 → 人选定 → 分档分析 → 可核验的单项目报告 → 周期横向抽象成规律库。

**当前阶段**：`L0`（采集 + 建池 + 去重 + **off 档体检报告**）。
L0 全链路**零 LLM**：不配置任何模型凭据也能跑出完整报告，成本为 0。

---

## 安装

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## 快速开始

```bash
python -m osslens init                                  # 建骨架 + config.yaml + patterns/seed.yaml
python -m osslens pool add deepseek-ai/DeepEP --channel classic
python -m osslens pool list                             # 按通道分别排序（hot / classic 不混排）
python -m osslens pool eligible                         # 深挖候选（热点需过观察期）
python -m osslens analyze deepseek-ai/DeepEP --depth auto --as-of 2026-11-02T00:00:00Z
python -m osslens cost                                  # 本周 / 本月台账
```

产物：

- `reports/<owner>__<repo>__<date>.md` —— 报告（五个区块，顺序固定）
- `data/featcards/<owner>__<repo>__<commit>.json` —— 特征卡 L0
- `data/pool/pool.jsonl` —— 观测序列（append-only）
- `data/costs/costs.jsonl` —— 调用 / 降级 / 预算事件（append-only）

## 环境变量

| 变量 | 作用 | 缺省行为 |
|---|---|---|
| `GITHUB_TOKEN` | GitHub API 鉴权（可选，未配置则 60 次/小时） | 匿名访问 |
| `OSSLENS_LLM_API_KEY` / `OSSLENS_LLM_BASE_URL` / `OSSLENS_LLM_MODEL` | LLM 三件套（L1 起使用） | **缺任一 → 自动降级 off，退出码 0** |

变量名由 `config.yaml` 的 `github_token_env` / `llm.*_env` 指定，代码不硬编码。

## 退出码

| 码 | 含义 |
|---|---|
| **0** | 完成（**可能已降级**，降级在报告「运行元数据」与 `costs.jsonl` 中可见） |
| 1 | 配置错误 / 真错误 |
| 2 | 参数错误 |

可选源失败、配额耗尽、预算拦截、未配 key **一律 0**。

## 数据布局

```
config.yaml                     # 唯一配置真源
patterns/                       # 规律库（L3 起）
data/ledger/selected.jsonl      # append-only
data/pool/pool.jsonl            # append-only 观测序列
data/snapshots/<owner>__<repo>/<date>.json
data/featcards/                 # 可丢弃、可重建
data/costs/costs.jsonl          # append-only
reports/
```

**真源**：`patterns/` · `data/ledger` · `data/pool` · `data/snapshots` · `data/costs` · `reports/`
**可丢弃**：`data/featcards/` · `site/` · 任何索引

## 幂等

同一 `--as-of` 连续两次运行，报告与特征卡**字节一致**：

```bash
sha256sum reports/deepseek-ai__DeepEP__2026-11-02.md
```

时间只来自 `--as-of`（或输入快照的 `fetched_at`），集合全部确定性排序，浮点 `round(x,4)`。

## 零 LLM 的取证方式

1. **运行时**：`analyze` 的 off 路径不构造任何模型客户端；测试在 httpx 传输层拦截真实外发，断言**零请求**。
2. **静态**：包内不存在任何模型服务商端点字面量（`chat/completions` 等）。

## 里程碑

| 阶段 | 状态 |
|---|---|
| L0 采集 / 建池 / 去重 / off 档报告 | ✅ 已完成 |
| L1 特征卡证据 + 依赖图 + 外部工具 + fast 档 | 未开始 |
| L2 档位四层 + 预算闸门 + 成本观测 + 定时 | 未开始（闸门数据结构已就位） |
| L3 模式召回 + 批量抽象 | 未开始 |
| L4 静态站点 | 未开始 |

## 开发

```bash
pip install -e ".[dev]"
pytest && ruff check . && ruff format --check . && mypy
```

详见 `CONTRIBUTING.md` 与 `CODEBUDDY.md`。
