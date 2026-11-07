# Changelog

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本号遵守语义化版本。

## [0.5.0] - 2026-11-07 · tag `l4`

L4：**静态只读站点**（最后一个功能阶段）。MD + JSON 真源 → 确定性 HTML/MD；零后端 / 零 LLM / 零网络 / 增量成本恒 ¥0。

### 新增

- `osslens/site.py`：`site` 命令（`--out` / `--as-of` / `--check`）、纯 MD `index.md` 索引、报告 / 特征卡 / 规律库 / 成本四块呈现、极简确定性 MD→HTML、`site --check` 差异清单
- `tests/test_l4.py` 20 条：四块呈现、五区块顺序、`--check` 不写盘、幂等、零网络双证据、空态、不展示敏感（含反向用例）
- `Layout.site_dir`；CLI 注册 `python -m osslens site`

### 实测

- 真实站点：15 个产物 / 104K；`site --check` 一致；同 `--as-of` 二次构建 sha256 全同；`costs.jsonl` 相对 `l3` **零改动**
- 零成本双证据：`site` 与 `site --check` 传输层拦截 `egress=[]`；`site.py` 静态无端点字面量、无 httpx 导入
- 空态诚实：`patterns/library.yaml = []` → 显示「规律库尚无条目（首次真实抽象未触发：inference 簇 5 < 6）」，`insufficient_samples` 可见
- 门禁：134 测试全绿 · `ruff check` · `ruff format --check` · `mypy strict`（16 source files）

### 文档

- 成本预算 §9（L4 ¥0 口径）、数据源手册 §10.6（D19 核查，采集环境分栏）、开发日志 L4、经验固化 E11（D28 三态口径）/ E12（`--check` 差异清单）、CODEBUDDY §9 L4 ✅ + 模块地图加 `site`

### 已知限制

- **规律库仍为空**：`library.yaml = []`，首次真实抽象未发生（inference 簇 5 < 6）；站点如实展示空态，不伪造条目
- **本阶段不做价格复核**（定价页正文未获得，E14 / D24）；单价只从 config 与报告「单价」行读取，未新增任何价格数字
- 收尾动作（`docs/功能总览.md` / 双方经验固化汇总 / remote / push / 真实 Actions run / 价格复核）**全部等 L4 验收后单独一轮**

## [0.4.0] - 2026-11-06 · tag `l3`

L3：**模式召回 + 四层抽象 + 增量 merge + 反例挖掘 + 抽象 run 成本闸门**。
交付的是**能力**不是漂亮内容：真实样本不足 S1 阈值时 `insufficient_samples` 产 0 条，真源纯净（S4）。

### 新增

- `osslens/patterns.py`：零 LLM 三态召回（硬 gating `domain.id` + 加权 Jaccard）、四层条目 schema 校验（L2 反例位 / L3 ≥2 跨域 / L4 下钻 L1 代码证据）、ops 六类增量 merge（`falsified` 不删）、反例候选挖掘、自检四问、`assert_storable` 真源纯净闸
- `osslens/abstract.py`：`cluster_run` / reconcile 编排、run 记录九字段（`run_id/type/cluster/trigger/input_projects/input_patterns/ops/llm_calls/created_at`）、`insufficient_samples` 合法终态、预算闸门（`estimate_safety_factor`）、跨域 L2 结构化摘要、同输入缓存、`off` 档零 LLM
- CLI `python -m osslens abstract [--as-of] [--cluster] [--off] [--dry-run] [--json]`；`init` 创建 `patterns/library.yaml`、`data/abstract/`
- `config.yaml` 新增 `domains:`（4 个可枚举 id + 子串归类规则）与 `abstract:` 四项阈值（簇内 ≥6 / 跨域 L2 ≥8 / 每 4 次簇内 run / 每 5 次 reconcile）；**不新建 `scope.yaml`**
- `tests/test_l3.py` 38 条（含三态、L2 缺反例位、L4 断链、缺对照组、合成条目、样本不足、幂等重放、预算拦截、缓存去重等「故意让它失败」反向用例）

### 变更

- `reports/` 按 S2 / 设计方案 v1.4 §8.2 精确化为**确定性 regenerate 产物**（非 append-only）；`CODEBUDDY §8` 已同步
- 真源新增 `patterns/library.yaml` / `patterns/ops.jsonl` / `data/abstract/runs.jsonl`

### 实测

- off 档采集 5 个真实 inference 仓库（`vllm` / `sglang` / `lmdeploy` / `text-generation-inference` / `lightllm`）+ 2 个 ai_infra，共 7 张真实特征卡；零 LLM（0 次模型调用、¥0）
- 真实 `abstract` run：`3f6e4c82e3b95f22`，`status=insufficient_samples`，样本 5 < 6，产 0 条、0 次 LLM；run 记录落 `data/abstract/runs.jsonl`
- 门禁：114 测试全绿 · `ruff check` · `ruff format --check` · `mypy strict`（15 source files）

### 已知限制

- **首次真实抽象未触发**：同簇真实样本 5 < 6（匿名 GitHub API 60/h 配额 + classic 入池门槛）；不硬凑、不降阈值、不用合成条目充数
- `patterns/library.yaml` 仍为 `[]`；L3/L4 级条目、跨域抽象、真实 reconcile、抽象 run 的真实 usage 回填均待样本达标后验证
- `site` / `docs/功能总览.md` 未实现（L4 / 收尾）

## [0.3.0] - 2026-11-05 · tag `l2`

L2：**strong 档实跑** + 档位四层跨周联动 + 估算安全系数 + D10 口径消歧 + 快照保留策略 + 定时建池 workflow + 成本闭环。

### 新增

- **strong 档接线**：`AVAILABLE_DEPTHS = {fast, strong}`；按档位取 model / thinking / `max_output_tokens` / purpose / system prompt（`STRONG_INSIGHT_SYSTEM`，代码资产）
- `Usage.reasoning_tokens` / 台账 `reasoning_tokens`：从 `completion_tokens_details` 回显，含在 `completion_tokens` 内按输出计费，不重复计费
- `budget.estimate_safety_factor = 1.3`（D12-2）：闸门按 `估算×系数` 判断，反向测试证明 L1 的 17,354→21,803 场景不再漏拦
- D10 口径字样 `本次分析的成本（不含开发期重复调用）；账户累计见 cost` 写进报告（`render.D10_WORDING`），`cost` 口径不变
- `osslens/retention.py`：按可再生性白名单分层的内容寻址去重 + 按期归档；`external/` 与全部真源受保护，默认 `dry_run=True`
- `.github/workflows/pool.yml`（D1 = C）：`ubuntu-24.04`、cron、`GITHUB_TOKEN`、`git pull --ff-only`、脏工作区显式跳过、按路径 add + push 真源
- `scripts/validate_workflow.py`：actionlint 不可用时的降级静态校验（13 项）+ 本地等价命令演练
- `tests/test_l2.py`：14 条（strong 接线 / 四层跨周 / 安全系数 / D10 / 保留策略），含「故意让它失败」反向用例

### 变更

- `config.yaml` / `DEFAULT_CONFIG` / `CONFIG_TEMPLATE` 新增 `llm.max_output_tokens`、`depth.budget.estimate_safety_factor`、`retention.*`
- `_run_insight` / `_record_call` / `_record_cache_hit` / `_record_blocked` / `_cost_line` 按实际档位参数化（原先硬编码 fast）
- `_events_excluding_current` 改为按 `INSIGHT_PURPOSES` 排除，保证 strong 报告重跑字节一致
- `test_no_llm_involved` 改为显式 `--depth off` 取证（strong 接入后 auto+凭据会合法调用）
- `.gitignore` 增 `data/cache_objects/` / `data/cache_archive/`（可再生缓存，不入库）

### 真实运行证据（非单测输出）

- `--depth strong` / `deepseek-v4-pro` / thinking=on / `json_object`：输入 21,910，输出 8,156（reasoning 7,801），**¥0.4174**，5 条带证据洞见，报告 5 区块，同 as-of 重跑 sha256 一致
- `costs.jsonl` 新增 strong `call` 事件（第 8 行）；第 9 行为重跑 `cache_hit`

### 已知账外支出 / 局限

- 开工前核对越界发的一次裸 httpx ping（`deepseek-v4-pro`，16 tok）**不补记台账**；`docs/成本预算.md` §0 显式披露「本节不是台账，不参与 cost 统计」，并沉淀 `docs/经验固化.md` E8
- `github.com/trending` 未获得（TCP 超时 0 字节，无 HTTP 响应）；`api.github.com` / `codeload.github.com` 可达 → 不阻塞建池，详见 `docs/数据源手册.md` §10.1
- actionlint 未安装，走降级静态校验，**不等同于 GitHub 真实 run**；未 push、未建 remote
- 76 测试 / 覆盖率 80%；详见 `docs/开发日志.md` L2 章节

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

- 62 个测试（+23），语句覆盖率 79%
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
