# osslens

> 低成本、可长期运行的开源项目深度分析系统。
> 建候选池 → 人选定 → 分档分析 → 可核验的单项目报告 → 周期横向抽象成规律库。

**当前阶段**：L0–L4 已交付；D31 私有远端发布接线完成，实现轮 v1.0 已启用 cron 定时建池、跨域抽象与静态站点三能力（检索 / 范式标签 / 并排对比）。路径 B 自动链已落地：真实调用间隔由 `auto_chain.analysis_interval_days` / `abstract_interval_days` 分别配置（默认 7 天、缺省继承旧键 `min_interval_days`），两段各自独立闸门；锚点随真源跨运行持久化；成本异常有报告头部区块 / Actions `::warning` / 站点红色 badge 三通道（只标注、不阻断）。当前 **209 tests**。详见 `docs/功能总览.md` 与 `docs/开发日志.md`。

- `off` 档：全链路**零 LLM**，不配置凭据也能跑出完整报告，成本 0。
- `fast` 档：真实调用 `deepseek-flash`；L1 实测单次 ≈ 22k tok / **¥0.046**，自动链最近一次真实调用 12,591 tok / **¥0.0278**（2026-11-13，见 `docs/成本预算.md` 与 `data/costs/costs.jsonl`）。

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
python -m osslens analyze deepseek-ai/DeepEP --depth fast --as-of 2026-11-03T00:00:00Z
python -m osslens cost                                  # 本周 / 本月台账
```

产物：

- `reports/<owner>__<repo>__<date>.md` —— 报告（v3：导读 + 6 章 + 附录 A/B，见 `docs/报告模板-v3.md`）
- `data/featcards/<owner>__<repo>__<commit>.json` —— 特征卡 L0
- `data/pool/pool.jsonl` —— 观测序列（append-only）
- `data/costs/costs.jsonl` —— 调用 / 降级 / 预算事件（append-only）

## 环境变量

| 变量 | 作用 | 缺省行为 |
|---|---|---|
| `GITHUB_TOKEN` | GitHub API 鉴权（可选，未配置则 60 次/小时） | 匿名访问 |
| `OSSLENS_LLM_API_KEY` / `OSSLENS_LLM_BASE_URL` | LLM 凭据（模型按档位由 `llm.models` 指定） | **缺任一 → 自动降级 off，退出码 0** |

变量名由 `config.yaml` 的 `github_token_env` / `llm.*_env` 指定，代码不硬编码。

## 退出码

| 码 | 含义 |
|---|---|
| **0** | 完成（**可能已降级**，降级在报告「运行元数据」与 `costs.jsonl` 中可见） |
| 1 | 配置或运行错误（配置加载失败 / 引擎错误 / 中断） |
| 2 | 参数错误 |

可选源失败、配额耗尽、预算拦截、未配 key **一律 0**。

## 数据布局

```
config.yaml                     # 唯一配置真源
patterns/                       # 规律库（L3 起）
data/ledger/selected.jsonl      # append-only
data/pool/pool.jsonl            # append-only 观测序列
data/snapshots/<owner>__<repo>/<date>.json   # 超 90 天 → .json.gz（内容不变）
data/featcards/                 # 可丢弃、可重建
data/costs/costs.jsonl          # append-only
reports/
```

**真源（append-only）**：`patterns/`（含 `ops.jsonl`）· `data/ledger` · `data/pool` · `data/costs` · `data/abstract/runs.jsonl` · `data/snapshots/**/external/`（不可再生）
**确定性 regenerate 产物**：`reports/` —— 同 `(repo, as-of)` 换档重跑允许覆盖，非 append-only
**可重建派生基线（入库、不得手写）**：`site/` —— 真源变更后重跑 `python -m osslens site` 并提交
**可再生缓存（可丢弃）**：`data/featcards/` · `data/llm_cache/` · `data/snapshots/**/src/` · 任何索引

完整分层以 `CODEBUDDY.md` §8 / `docs/设计方案.md` v1.5 §8.2 为准（D15）。

## 幂等

同一 `--as-of` 连续两次运行，报告与特征卡**字节一致**：

```bash
sha256sum reports/deepseek-ai__DeepEP__2026-11-02.md
```

时间只来自 `--as-of`（或输入快照的 `fetched_at`），集合全部确定性排序，浮点 `round(x,4)`。

## 零 LLM 的取证方式（off 档）

1. **运行时**：off 路径不构造任何模型客户端；测试在 httpx 传输层拦截真实外发，断言**零请求**。
2. **静态**：`/chat/completions` 字面量只允许出现在 `osslens/llm.py`（有测试守住）。

fast 档的真实调用证据是 `usage` 回显：`prompt_tokens / prompt_cache_hit_tokens / completion_tokens`
直接写进 `data/costs/costs.jsonl`，报告「成本说明」行与 `cost` 命令都能对上。

## 里程碑

| 阶段 | 状态 |
|---|---|
| L0 采集 / 建池 / 去重 / off 档报告 | ✅ 已完成 |
| L1 特征卡证据 + 依赖图 + 外部工具 + fast 档 | ✅ 已完成 |
| L2 档位四层 + 预算闸门 + 成本观测 + 定时 | ✅ 已完成（strong 实跑 ¥0.4174） |
| L3 模式召回 + 批量抽象 | ✅ 已完成（真源纯净，样本不足时 `insufficient_samples` 空态） |
| L4 静态站点 | ✅ 已完成（静态只读，零 LLM / 零网络） |
| 收尾全景定稿 | ✅ 已完成（`docs/功能总览.md`） |
| D31 私有远端发布接线 | ✅ 已完成（私有仓库 / remote / push / 真实 Actions run #2 Success；只推 main、远端 tag 0） |
| 实现轮 v1.0 | ✅ 已完成（cron 启用 · retention 接线 · 跨域抽象 · paradigm_tags · 静态三能力） |

## 开发

```bash
pip install -e ".[dev]"
pytest && ruff check . && ruff format --check . && mypy
```

详见 `CONTRIBUTING.md` 与 `CODEBUDDY.md`。
