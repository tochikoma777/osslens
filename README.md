# osslens

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![auto chain](https://github.com/tochikoma777/osslens/actions/workflows/auto.yml/badge.svg)](https://github.com/tochikoma777/osslens/actions/workflows/auto.yml)
[![pool](https://github.com/tochikoma777/osslens/actions/workflows/pool.yml/badge.svg)](https://github.com/tochikoma777/osslens/actions/workflows/pool.yml)

**把开源项目变成可核验的深度报告，并把一次次分析沉淀成规律库——成本可控，长期可跑。**

`osslens` 是一条从候选池到规律库的流水线：建池 → 选定 → 分档分析 → 生成报告 → 周期抽象。每一步的产物都落到磁盘、可复核。不用配置任何 LLM 凭据也能跑通（`off` 档零成本）；配置了就按档位调用、按预算闸门计费。同一时间基准重跑，报告逐字节一致。

```
候选池 ──选定──▶ 分档分析 ──▶ 深度报告 ──┐
  ▲                              │        │
  │ GitHub Search 发现           ▼        ▼
  └────────────── 规律库 ◀── 周期抽象   静态站点
```

## 为什么用它

分析一个开源项目，难的从来不是"查资料"，而是三件事：

- **结论要能回到证据**。报告里的每条判断都应指向具体的源码行与来源，而不是一段无法追溯的摘要。
- **成本要有边界**。批量分析最怕 LLM 账单失控，因此需要档位、额度、调用次数与预算闸门，而不是"调用再说"。
- **过程要能长期运行**。新项目出现后，应当自动进入候选池并按间隔触发分析，而不是每次手工搬运。

`osslens` 把这三件事固化成可重复、可审计的流程。它不评价项目好坏，只产出**可核验的事实与判断依据**。

## 核心特性

- **零成本起步**：`off` 档不构造任何模型客户端，不配置凭据也能产出完整报告，全程零 LLM、零费用。
- **可核验的报告**：v3 报告为「导读 + 6 章 + 附录 A/B」结构，关键设计决策（ADR）带 `file:line` 证据，未知项如实标注。
- **确定性**：时间只来自 `--as-of`，集合确定性排序，浮点 `round(x,4)`；同一时间基准重跑，报告与特征卡字节一致。
- **成本闸门**：周/月 token 额度、单次 prompt 上限、单次调用次数上限与安全系数（默认 1.3）共同兜底，异常以报告头 / Actions 警告 / 站点红标三通道标注，不阻断。
- **自动化**：GitHub Actions 每日定时建池（含 GitHub Search 零 LLM 发现）与自动分析 / 抽象，分析、抽象各有独立间隔闸门。
- **静态站点**：`site` 生成只读站点，提供搜索、范式标签、并排对比与技术选型视图；零网络、零 LLM。
- **真源与派生分离**：`patterns/`、`pool`、`costs`、`snapshots/external` 等为 append-only 真源；报告可确定性重建；站点是入库的派生基线，不手写。

## 快速开始

### 安装

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 零成本跑通一遍

```bash
python -m osslens init                                   # 建骨架 + config.yaml + patterns/seed.yaml
python -m osslens pool add deepseek-ai/DeepEP --channel classic
python -m osslens pool list                              # 按通道分别排序（hot / classic 不混排）
python -m osslens pool eligible                          # 深挖候选（热点需过观察期）
python -m osslens analyze deepseek-ai/DeepEP --depth off --as-of 2026-11-18T00:00:00Z
python -m osslens cost                                   # 本周 / 本月台账
```

`off` 档会跳过源码采集与模型调用，产出的是「骨架完整、证据为空」的报告——适合先验证流程。要看真实证据，配置 LLM 凭据后把 `--depth off` 换成 `--depth fast`。

### 配置真实调用（可选）

```bash
export OSSLENS_LLM_API_KEY='...'
export OSSLENS_LLM_BASE_URL='https://.../v1'
python -m osslens analyze deepseek-ai/DeepEP --depth fast --as-of 2026-11-18T00:00:00Z
```

`fast` 档实测单次约 2.2 万 token / ¥0.046；自动链最近一次真实调用 12,591 token / ¥0.0278（2026-11-13）。单价来自 `config.yaml`，代码不内置价格。台账：`data/costs/costs.jsonl`。

### 产出

| 产物 | 路径 | 说明 |
|---|---|---|
| 深度报告 | `reports/<owner>__<repo>__<date>.md` | v3：导读 + 6 章 + 附录 A/B，见 `docs/报告模板-v3.md` |
| 特征卡 | `data/featcards/<owner>__<repo>__<commit>.json` | L0 证据与依赖图，可重建 |
| 观测序列 | `data/pool/pool.jsonl` | append-only |
| 成本台账 | `data/costs/costs.jsonl` | 调用 / 降级 / 预算事件，append-only |
| 静态站点 | `site/` | `python -m osslens site` 生成，入库的派生基线 |

## 命令一览

| 命令 | 作用 | 是否调用 LLM |
|---|---|---|
| `init` | 初始化工作区骨架与配置 | 否 |
| `pool add` | 抓取快照并追加观测 | 否 |
| `pool list` / `pool eligible` | 按通道排序 / 深挖候选 | 否 |
| `pool discover` | GitHub Search 自动发现候选 | 否 |
| `analyze <owner/repo>` | 产出报告与特征卡 | 取决于 `--depth` |
| `abstract` | L3 规律抽象（簇内 / 跨域） | 可 `--off` 零 LLM 召回 |
| `cost` | 查看本周 / 本月台账 | 否 |
| `site` | 生成 / 校验静态站点 | 否 |
| `retention` | 缓存保留策略（默认 dry-run） | 否 |

所有子命令都支持 `--help`；`--root` 可指定工作区（默认当前目录）。`analyze` 还支持 `--dry-run`（只打印决策）、`--no-sources`（跳过源码采集）、`--as-of`（指定时间基准）。

## 配置

唯一配置真源是 `config.yaml`（`init` 时生成）。常用项：

| 配置项 | 默认值 | 含义 |
|---|---|---|
| `llm.models.fast` / `strong` | `deepseek-flash` / `deepseek-v4-pro` | 分档模型名 |
| `depth.weekly_quota.fast` | `5` | 每周 fast 档分析次数上限 |
| `depth.budget.weekly_tokens` | `2,000,000` | 周 token 预算 |
| `depth.budget.monthly_tokens` | `6,000,000` | 月 token 预算 |
| `depth.budget.estimate_safety_factor` | `1.3` | 估算放大系数，防止低估导致漏拦 |
| `auto_chain.analysis_interval_days` | `1` | 自动分析的最小真实调用间隔（天） |
| `auto_chain.abstract_interval_days` | `7` | 自动抽象的最小真实调用间隔（天） |
| `report.profile` | `adoption_due_diligence` | 报告阅读档位（另有 `architecture_learning` / `contributor_onboarding`） |
| `abstract.cluster_min_new_projects` | `6` | 同簇新增真实项目数触发阈值 |

### 环境变量

| 变量 | 作用 | 缺省行为 |
|---|---|---|
| `GITHUB_TOKEN` | GitHub API 鉴权（可选，未配置则 60 次/小时） | 匿名访问 |
| `OSSLENS_LLM_API_KEY` / `OSSLENS_LLM_BASE_URL` | LLM 凭据（模型按档位由 `llm.models` 指定） | **缺任一 → 自动降级 `off`，退出码 0** |

变量名由 `config.yaml` 的 `github_token_env` / `llm.*_env` 指定，代码不硬编码。

## 数据布局

```
config.yaml                                              # 唯一配置真源
patterns/                                                # 规律库（L3 起）
data/ledger/selected.jsonl                               # append-only
data/pool/pool.jsonl                                     # append-only 观测序列
data/snapshots/<owner>__<repo>/<date>.json               # 超 90 天 → .json.gz（内容不变）
data/snapshots/<owner>__<repo>/<date>/external/          # 不可再生真源
data/featcards/                                          # 可丢弃、可重建
data/costs/costs.jsonl                                   # append-only
reports/                                                 # 可确定性重建
site/                                                    # 派生基线，入库但不手写
```

| 类别 | 路径 | 处置规则 |
|---|---|---|
|真源（append-only）| `patterns/`（含 `ops.jsonl`）、`data/ledger`、`data/pool`、`data/costs`、`data/abstract/runs.jsonl`、`data/snapshots/**/external/` | 只追加、不修改、不删除 |
|确定性重建产物| `reports/` | 同 `(repo, as-of)` 重跑允许覆盖 |
|派生基线（入库）| `site/` | 真源变更后重跑 `python -m osslens site` 并提交，不手写 |
|可再生缓存（可丢弃）| `data/featcards/`、`data/llm_cache/`、`data/snapshots/**/src/`、任何索引 | 可重建；`src/` 已从版本控制剔除 |

完整分层以 `CODEBUDDY.md` §8 / `docs/设计方案.md` v1.5 §8.2 为准（D15）。

## 设计保证

### 幂等

同一 `--as-of` 连续两次运行，报告与特征卡**字节一致**：

```bash
# 连续跑两次同一命令，再看 sha256 是否相同
python -m osslens analyze deepseek-ai/DeepEP --depth off --as-of 2026-11-18T00:00:00Z
sha256sum reports/deepseek-ai__DeepEP__2026-11-18.md
```

时间只来自 `--as-of`（或输入快照的 `fetched_at`），集合全部确定性排序，浮点 `round(x,4)`。

### 零 LLM 的取证方式（`off` 档）

1. **运行时**：`off` 路径不构造任何模型客户端；测试在 httpx 传输层拦截真实外发，断言**零请求**。
2. **静态**：`/chat/completions` 字面量只允许出现在 `osslens/llm.py`（有测试守住）。

`fast` 档的真实调用证据是 `usage` 回显：`prompt_tokens / prompt_cache_hit_tokens / completion_tokens` 直接写进 `data/costs/costs.jsonl`，报告「成本说明」行与 `cost` 命令都能对上。

### 退出码

| 码 | 含义 |
|---|---|
| **0** | 完成（**可能已降级**，降级在报告「运行元数据」与 `costs.jsonl` 中可见） |
| 1 | 配置或运行错误（配置加载失败 / 引擎错误 / 中断） |
| 2 | 参数错误 |

可选源失败、配额耗尽、预算拦截、未配 key 一律返回 **0**。

## 项目现状

L0–L4 能力已全部交付；当前 **231 个测试**、站点 **25 个产物**，门禁全绿。仓库以 MIT 许可公开，手动触发与定时任务均在 GitHub Actions 上持续运行。

| 阶段 | 状态 |
|---|---|
| L0 采集 / 建池 / 去重 / off 档报告 | 已完成 |
| L1 特征卡证据 + 依赖图 + 外部工具 + fast 档 | 已完成 |
| L2 档位四层 + 预算闸门 + 成本观测 + 定时 | 已完成（strong 实跑 ¥0.4174） |
| L3 模式召回 + 批量抽象 | 已完成（样本不足时为空态 `insufficient_samples`） |
| L4 静态站点 | 已完成（检索 / 标签 / 对比 / 选型视图，零 LLM / 零网络） |
| 实现轮 v1.0 | 已完成（cron 启用 · retention 接线 · 跨域抽象 · 静态三能力） |
| 合规重构 | 已完成（MIT 许可 · 公开仓库 · 历史剔除第三方源码切片 · tag 重打） |

已知局限：规律库样本仍在积累，暂无反例条目，跨域抽象 / reconcile 多为空态。详见 `docs/功能总览.md` §6。

## 文档导航

- [功能总览](docs/功能总览.md) —— 五阶段能力、命令总表、数据分层、已知局限
- [设计方案](docs/设计方案.md) —— what / why，架构与阈值依据
- [执行手册](docs/执行手册.md) —— how，运行与维护
- [报告模板 v3](docs/报告模板-v3.md) —— 报告结构与各章合同
- [成本预算](docs/成本预算.md) —— 价表来源与成本口径
- [数据源手册](docs/数据源手册.md) —— 各来源的取用规则
- [经验固化](docs/经验固化.md) —— 本项目踩过并固化的工程教训
- [审查报告](docs/审查报告/) —— 历次只读审查报告（本地留存，不入库）

## 开发

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy
```

提交与红线约定见 [CONTRIBUTING.md](CONTRIBUTING.md)；Agent 在本仓库的工作方式见 [CODEBUDDY.md](CODEBUDDY.md)。

## 许可

[MIT](LICENSE) © 2026 tochikoma777
