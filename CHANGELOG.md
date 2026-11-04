# Changelog

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本号遵守语义化版本。

## [0.2.0] - 2026-11-03 · tag `l1`

L1：特征卡证据 + 依赖图 + 外部资料 fail-closed + **fast 档真实调用**。

### 新增

- 特征卡证据层：`parallel.hits` / `cache.hits` / `hardware.*` 每个 `true` 带 `file:line:snippet`，证据来自源码切片逐行扫描
- `deps.graph` 由空结构填充为内部模块 import 边；报告内嵌 Mermaid（`graph TD`，节点/边排序，空态显式）
- `probe_external`：DeepWiki 探测器，**只看正文含 ≥3 个仓库内真实路径**；429/模板页 → fail-closed，原文与判定元数据分文件存放（四元组）
- fast 档接线：httpx 直连 `/chat/completions`，调用前裁剪、`json_object` 阶梯、判废规则、usage 回填
- 结果缓存（`data/llm_cache/`）：同输入复用 → 省钱 + 幂等
- `cost` 增加缓存命中分项、按用途分项、异常标注
- 报告「运行元数据」内追加成本说明三行（不新增区块）
- `depth.budget.max_calls_per_run`（默认 12）：超限硬停、退出码 0、候选不丢
- `pool add` 门槛标注（`below_threshold`），watchlist 豁免
- 维护状态阈值外置 `featcard.maintenance`（90 / 365）

### 变更

- `llm.model_env` → `llm.models.{fast,strong}`（旧键被忽略，不报错）
- `price_table` 三值：`cache_hit_per_1m` / `prompt_per_1m` / `completion_per_1m`（CNY，高峰价）
- `resolve_depth(llm_available)` → `available_depths`

### 工程

- 62 个测试（+23），语句覆盖率 81%
- 真实运行：DeepEP fast 档，22,304 tok / ¥0.0459 / 12 条带证据洞见 / 8 条依赖边
- 已知限制见 `docs/开发日志.md` §L1-4

## [0.1.0] - 2026-11-02 · tag `l0`

L0：采集 + 建池 + 去重 + **off 档体检报告**。全链路零 LLM。

### 新增

- `python -m osslens init`：工作区骨架、`config.yaml`、`patterns/seed.yaml`（已存在则跳过，不覆盖）
- `python -m osslens pool add`：真实 GitHub 快照（stars/forks/commits/contributors/languages/tree）→ 追加观测
- `python -m osslens pool list`：hot / classic **分通道** z-score 打分排序
- `python -m osslens pool eligible`：观察期（热点 ≥7 天）与通道阈值判定，输出排除原因
- `python -m osslens analyze`：off 档体检报告（运行元数据 / 体检事实 / 特征卡摘要 / 洞见 `—` / 外部资料）
- `python -m osslens cost`：本周 / 本月 token、费用、按档位分布、降级与拦截次数、预算剩余
- 档位四层解析：L1 通道基线 → 凭据 / 实现能力 → L2 周配额 → L3 预算闸门 → L4 override
- 降级**双写**留痕：报告「运行元数据」块 + `data/costs/costs.jsonl`
- 特征卡 L0（确定性、零 LLM），`parallel/cache/hardware` 无证据一律 `false`；`deps.graph` 结构就位（空）

### 工程

- `pyproject.toml`（setuptools + httpx + PyYAML），`[dev]` 含 pytest / ruff / mypy / respx
- 门禁：`pytest` · `ruff check` · `ruff format --check` · `mypy --strict`
- 39 个测试，语句覆盖率 84%（`pool.py` 95%、`config.py` 88%、`collect.py` 87%）

### 已知限制

- `used_by` / `deps.*` / `loc_total` / `internal_edge_count` / `issue_close_ratio_90d` 为 `null`（L0 不读源码、无可公开 API）
- 热点通道的 7 日增量需 ≥2 次观测；首次入池必为 `0`（设计如此，不估算）
- 外部工具（DeepWiki / Zread）未接线，报告标注「不可用（未索引）」
- `abstract` / `site` / 模式召回 未实现（L3 / L4）
