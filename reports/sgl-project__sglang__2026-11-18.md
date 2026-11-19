# sgl-project/sglang 深度分析

> 阅读档位：架构学习（profile=architecture_learning）
> 注意力预算：定位 20 / 架构 30 / 抽象 15 / ADR 20 / 扩展 5 / 经验卡 10 / 工程维护 0
> 证据约定：[事实] 确定性提取 · [判断] 有 file:line 或文档锚点 · [未获得] 当前未采集

## 导读

> **是什么**：SGLang is a high-performance serving framework for large language models and multimodal models.
> **架构一句话**：[判断] 顶层以 `python`、`test`、`docs` 为主，入口为 `python/sglang/cli/main.py`（静态结构判断，未做动态跟踪）。
> **最大风险**：Top1 贡献者占比 7.34%，决策集中度需关注
> **不适合**：需要稳定 API/长期支持承诺的场景，请先核对发布节奏与维护状态；依赖链许可证与权重许可能力当前未采集，不能据此做出商用结论。

## 1. 项目定位与目标

[事实] sgl-project/sglang 属于 `inference` 领域、`classic` 通道，主语言 Python（86%），39,021 stars / 10,590 forks。

[事实] 项目自述：SGLang is a high-performance serving framework for large language models and multimodal models.。

[事实] README 摘要：SGLang Simulator reuses SGLang's scheduler and cache implementation while replacing model forward execution with a latency predictor. It supports timestamped trace replay, synthetic workloads, hierarchical cache simulation, and serving-compatible metrics without loading model weights. See the SGLang Simulator advanced-feature guide for the user-facing setup and serving workflow. SGLang Simulator tracks the current SGLang `main` branch and maintains compatibility。

- **目标用户**：[判断] 模型工程师 / 推理基础设施开发者；应用与平台开发者；终端用户与性能调优人员
- **替代方案与差异**：[未获得] 本次未采集竞品对比与 roadmap，不得据此推断「没有替代品」。
- **不解决什么**：[未获得] 没有路线图与 issue 语料，无法可靠界定能力边界。

[判断] 阶段信号：仓库已存在 1,045 天，近一年发布 25 个版本，最近提交距今 0 天，维护状态「active」。这只说明是否仍在维护，不等于成熟度结论。

## 2. 架构全景

### 2.1 上下文边界

[判断] 架构说明文档：`benchmark/blog_v0_2/README.md`, `benchmark/deepseek_v3/README.md`, `python/sglang/kernels/README.md`, `python/sglang/kernels/ops/diffusion/README.md`, `python/sglang/multimodal_gen/apps/ComfyUI_SGLDiffusion/README.md`；边界结论来自文档与目录结构，未经运行验证。
[事实] 硬件/内核线索：vendors=[amd, nvidia]、kernel_langs=[cuda, hip, tilelang, triton]。

### 2.2 模块职责

| 模块 | 文件数 | 职责（启发式） |
|---|---:|---|
| `python` | 6,734 | 语言绑定与封装 |
| `test` | 3,445 | 测试与用例 |
| `docs` | 692 | 文档 |
| `rust` | 308 | 业务实现（职责需人工确认） |
| `sgl-router` | 292 | 业务实现（职责需人工确认） |

### 2.3 一次调用的路径（运行时视图）

[判断] 静态推断：`python/sglang/cli/main.py`, `python/sglang/kernels/jit/__main__.py`, `python/sglang/multimodal_gen/apps/ComfyUI_SGLDiffusion/convert/__main__.py`, `python/sglang/multimodal_gen/apps/webui/main.py`, `python/sglang/multimodal_gen/runtime/entrypoints/cli/main.py`, `python/sglang/srt/debug_utils/comparator/__main__.py`, `python/sglang/srt/debug_utils/schedule_simulator/__main__.py`, `python/sglang/test/cuda_graph_lifetime/__main__.py`, `rust/sglang-api-codegen/src/main.rs`, `scripts/playground/disaggregation/cli.py`, `sgl-router/src/main.rs`, `sgl-router/tests/component/main.rs`, `sgl-router/tests/proxy/main.rs` → 输出。内部 import 边约 0 条，只用于判断调用方向；**未做运行时跟踪**，参数与分支需读源码确认。

### 2.4 数据与控制流

[事实] 并行轴命中 CP, DP, SP, TP；缓存轴命中 paged, prefix_reuse, radix（证据见附录 A）。

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

## 3. 核心抽象与契约

[未获得] 本次源码切片未识别到显式接口/注册模式；这不等于项目没有抽象层，只说明当前采集粒度不足。

入口候选（可作为契约阅读起点）：`python/sglang/cli/main.py`、`python/sglang/kernels/jit/__main__.py`、`python/sglang/multimodal_gen/apps/ComfyUI_SGLDiffusion/convert/__main__.py`、`python/sglang/multimodal_gen/apps/webui/main.py`、`python/sglang/multimodal_gen/runtime/entrypoints/cli/main.py`、`python/sglang/srt/debug_utils/comparator/__main__.py`、`python/sglang/srt/debug_utils/schedule_simulator/__main__.py`、`python/sglang/test/cuda_graph_lifetime/__main__.py`、`rust/sglang-api-codegen/src/main.rs`、`scripts/playground/disaggregation/cli.py`、`sgl-router/src/main.rs`、`sgl-router/tests/component/main.rs`、`sgl-router/tests/proxy/main.rs`

## 4. 关键设计决策（ADR）

每条固定六字段：决策 / 替代 / 代价 / 证据 / 可复用规则 / 边界·反模式。

### ADR-1 · t1: 模拟器复用 SGLang 调度器与缓存，仅替换前向为延迟预测

- **决策**：模拟器复用 SGLang 调度器与缓存，仅替换前向为延迟预测
- **替代**：另建独立仿真栈或直接跑真实模型
- **代价**：仿真结果依赖预测器精度，需重新基线校准
- **证据**：`tools/sglang-simulator/README.md:3`
- **可复用规则**：复用生产调度与缓存代码做仿真，只替换最贵的前向执行
- **边界/反模式**：预测器数据未覆盖的模型/硬件组合下误差不可控

### ADR-2 · t2: 仿真器强制单进程 tp=ep=dp=pp=1，拓扑仅在配置中建模

- **决策**：仿真器强制单进程 tp=ep=dp=pp=1，拓扑仅在配置中建模
- **替代**：按真实并行度启动物理 worker 做仿真
- **代价**：无法验证真实多卡通信与并行正确性
- **证据**：`tools/sglang-simulator/README.md:191`
- **可复用规则**：仿真只建模拓扑不启动物理并行，降低 CPU 侧开销
- **边界/反模式**：需要验证通信/并行实现本身时不可用

### ADR-3 · t3: 前缀缓存命中精度绑定 max_total_tokens 与真实日志一致

- **决策**：前缀缓存命中精度绑定 max_total_tokens 与真实日志一致
- **替代**：用独立估算的 KV 容量做仿真
- **代价**：每次对比需手工同步真实服务启动参数
- **证据**：`tools/sglang-simulator/README.md:255`
- **可复用规则**：缓存仿真参数必须从生产启动日志复制，避免淘汰时机漂移
- **边界/反模式**：容量动态调整或异构部署时日志值不具代表性

### ADR-4 · t4: 预测器迁移到 AISimulate 且不保留旧名兼容层

- **决策**：预测器迁移到 AISimulate 且不保留旧名兼容层
- **替代**：保留 aiconfigurator 别名做静默回退
- **代价**：旧配置直接报错，用户须手工迁移
- **证据**：`tools/sglang-simulator/README.md:99`
- **可复用规则**：依赖更名时显式报错而非静默回退，避免隐性数值漂移
- **边界/反模式**：面向大量存量外部用户且无法批量改配置时成本过高

### ADR-5 · t5: 统一可插拔前缀缓存框架覆盖 Full/SWA 等多种注意力

- **决策**：统一可插拔前缀缓存框架覆盖 Full/SWA 等多种注意力
- **替代**：为每种注意力各写一套缓存实现
- **代价**：抽象层增加组件组合与调试复杂度
- **证据**：`python/sglang/srt/mem_cache/unified_cache/components/README.md:3`
- **可复用规则**：用组件化框架统一多注意力变体的缓存，减少重复实现
- **边界/反模式**：单一注意力形态的轻量服务引入框架属过度设计

### ADR-6 · t6: 缓存文件用 O_DIRECT 绕过 OS page cache

- **决策**：缓存文件用 O_DIRECT 绕过 OS page cache
- **替代**：依赖页缓存加速缓存文件读取
- **代价**：失去页缓存命中，小 IO 读放大
- **证据**：`python/sglang/srt/mem_cache/storage/nixl/README.md:446`
- **可复用规则**：大块 KV 落盘用直接 IO 避免挤占主机内存
- **边界/反模式**：小随机读或低内存压力场景直接 IO 反而更慢

## 5. 扩展与改造路径

[未获得] 未识别到显式插件/注册点。

[判断] 新增能力的静态路径（需按实际代码复核）：

1. 在入口处接入参数/配置（入口候选：`python/sglang/cli/main.py`, `python/sglang/kernels/jit/__main__.py`, `python/sglang/multimodal_gen/apps/ComfyUI_SGLDiffusion/convert/__main__.py`, `python/sglang/multimodal_gen/apps/webui/main.py`, `python/sglang/multimodal_gen/runtime/entrypoints/cli/main.py`, `python/sglang/srt/debug_utils/comparator/__main__.py`, `python/sglang/srt/debug_utils/schedule_simulator/__main__.py`, `python/sglang/test/cuda_graph_lifetime/__main__.py`, `rust/sglang-api-codegen/src/main.rs`, `scripts/playground/disaggregation/cli.py`, `sgl-router/src/main.rs`, `sgl-router/tests/component/main.rs`, `sgl-router/tests/proxy/main.rs`, `python`）；
2. 复用上表中的注册/分派结构，实现新的后端或适配器；
3. 补对应测试与文档，再走发布流程。

- 扩展文档：[未获得]
- 改造成本：[未获得] 需要先确认契约稳定性与测试覆盖，本报告不估算人日。

## 6. 经验卡

### 经验 1 · 复用生产调度与缓存代码做仿真，只替换最贵的前向执行

- **证据**：`tools/sglang-simulator/README.md:3`（来自 sgl-project/sglang）
- **适用边界**：预测器数据未覆盖的模型/硬件组合下误差不可控
- **反模式**：在边界之外照搬「模拟器复用 SGLang 调度器与缓存，仅替换前向为延迟预测」，代价会变成「仿真结果依赖预测器精度，需重新基线校准」
- **如果我来做**：先确认边界成立，再选择「模拟器复用 SGLang 调度器与缓存，仅替换前向为延迟预测」而非「另建独立仿真栈或直接跑真实模型」

### 经验 2 · 仿真只建模拓扑不启动物理并行，降低 CPU 侧开销

- **证据**：`tools/sglang-simulator/README.md:191`（来自 sgl-project/sglang）
- **适用边界**：需要验证通信/并行实现本身时不可用
- **反模式**：在边界之外照搬「仿真器强制单进程 tp=ep=dp=pp=1，拓扑仅在配置中建模」，代价会变成「无法验证真实多卡通信与并行正确性」
- **如果我来做**：先确认边界成立，再选择「仿真器强制单进程 tp=ep=dp=pp=1，拓扑仅在配置中建模」而非「按真实并行度启动物理 worker 做仿真」

### 经验 3 · 缓存仿真参数必须从生产启动日志复制，避免淘汰时机漂移

- **证据**：`tools/sglang-simulator/README.md:255`（来自 sgl-project/sglang）
- **适用边界**：容量动态调整或异构部署时日志值不具代表性
- **反模式**：在边界之外照搬「前缀缓存命中精度绑定 max_total_tokens 与真实日志一致」，代价会变成「每次对比需手工同步真实服务启动参数」
- **如果我来做**：先确认边界成立，再选择「前缀缓存命中精度绑定 max_total_tokens 与真实日志一致」而非「用独立估算的 KV 容量做仿真」

### 经验 4 · 依赖更名时显式报错而非静默回退，避免隐性数值漂移

- **证据**：`tools/sglang-simulator/README.md:99`（来自 sgl-project/sglang）
- **适用边界**：面向大量存量外部用户且无法批量改配置时成本过高
- **反模式**：在边界之外照搬「预测器迁移到 AISimulate 且不保留旧名兼容层」，代价会变成「旧配置直接报错，用户须手工迁移」
- **如果我来做**：先确认边界成立，再选择「预测器迁移到 AISimulate 且不保留旧名兼容层」而非「保留 aiconfigurator 别名做静默回退」

### 经验 5 · 用组件化框架统一多注意力变体的缓存，减少重复实现

- **证据**：`python/sglang/srt/mem_cache/unified_cache/components/README.md:3`（来自 sgl-project/sglang）
- **适用边界**：单一注意力形态的轻量服务引入框架属过度设计
- **反模式**：在边界之外照搬「统一可插拔前缀缓存框架覆盖 Full/SWA 等多种注意力」，代价会变成「抽象层增加组件组合与调试复杂度」
- **如果我来做**：先确认边界成立，再选择「统一可插拔前缀缓存框架覆盖 Full/SWA 等多种注意力」而非「为每种注意力各写一套缓存实现」

## 附录 A 证据索引与未知项

### A1. 代码证据索引

| id | 决策 | 证据 |
|---|---|---|
| t1 | 模拟器复用 SGLang 调度器与缓存，仅替换前向为延迟预测 | `tools/sglang-simulator/README.md:3` |
| t2 | 仿真器强制单进程 tp=ep=dp=pp=1，拓扑仅在配置中建模 | `tools/sglang-simulator/README.md:191` |
| t3 | 前缀缓存命中精度绑定 max_total_tokens 与真实日志一致 | `tools/sglang-simulator/README.md:255` |
| t4 | 预测器迁移到 AISimulate 且不保留旧名兼容层 | `tools/sglang-simulator/README.md:99` |
| t5 | 统一可插拔前缀缓存框架覆盖 Full/SWA 等多种注意力 | `python/sglang/srt/mem_cache/unified_cache/components/README.md:3` |
| t6 | 缓存文件用 O_DIRECT 绕过 OS page cache | `python/sglang/srt/mem_cache/storage/nixl/README.md:446` |
| t7 | 基准默认关闭 radix 缓存以隔离纯计算性能 | `benchmark/blog_v0_2/README.md:30` |

- 置信度：med
- 架构范式标签：广适配、深优化、缓存复用

### A2. 外部资料

- 来源：deepwiki
- url：https://deepwiki.com/sgl-project/sglang
- fetched_at：2026-11-19T15:05:00Z
- sha256：`7b2d5e929f450eb55198bbfffd156aa9a0fd7fa8991a6a851996f933af26916e`
- 判定：hit — 正文含 3 个仓库内真实路径（阈值 3）
- 原文快照：`source.txt`（与判定元数据分文件存放）

### A3. 未获得项

- 依赖链许可证、模型权重/数据许可、CLA —— 未采集；
- issue/PR 响应质量、CI 运行结果 —— 未采集；
- roadmap、竞品对比、用户画像 —— 未采集；
**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算


## 附录 B 许可证 / 维护 / 工程 / 成本

### B1. 许可证与合规风险

[事实] 主许可证 **Apache-2.0**；组织类型 —；治理文档：有。

[未获得] 依赖链是否存在 GPL/AGPL、模型权重与数据集许可、CLA 要求；这些必须人工或由后续数据源补齐，本报告不给出「可商用」结论。

### B2. 维护状态与风险

[事实] 贡献者 447 人，Top1 占比 7.34%；近 90 天 / 365 天提交 2,000 / 2,000 次；最近提交距今 0 天，维护状态「active」。

- Top1 贡献者占比 7.34%，决策集中度需关注

### B3. 运行与工程体系

[事实] 仓库约 12,388 个文件、166.0 MiB；本次采集 20 个源码切片（tarball `c0a6b121e2f6eb95`）。
[事实] 语言构成：Assembly 0.03%、C 0.10%、C++ 1.42%、CMake 0.02%、CSS 0.01%、Cuda 4.51%、Dockerfile 0.13%、Go Template 0.03%、HIP 0.06%、HTML 0.01%、JavaScript 0.09%、Jinja 0.03%、Jupyter Notebook 0.01%、Makefile 0.00%、Metal 0.02%、Python 86.35%、Rust 6.74%、Shell 0.39%、Vim Script 0.00%、mupad 0.07%；硬件 vendors=[amd, nvidia]、kernel_langs=[cuda, hip, tilelang, triton]。

[未获得] 构建脚本、依赖安装、测试体系、CI/CD、配置与 secret 管理未采集；本报告不能回答「能否在目标环境跑起来」。

**特征卡已知限制**：

- 证据来自 20 个源码切片的逐行扫描，未覆盖文件不计入
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B4. 运行元数据与成本

| 项 | 值 |
|---|---|
| 仓库 | sgl-project/sglang |
| commit | `e0decbc3388fbc0bf02882311df5a1aa33502018` |
| 分析基准时间 (as-of) | 2026-11-18T00:00:00Z |
| 通道 / 领域 | classic / inference |
| 请求档位 (requested_depth) | fast |
| **实际档位** (actual_depth) | fast |
| 降级原因 (reason) | manual_override — 人工 override |
| 配额状态 (quota_state) | strong 0/1、fast 13/5（周起点 2026-11-16）；tokens 周 194291/2000000、月 304441/6000000（月起点 2026-11-01） |
| 快照 sha256 | `b7f6936a9758bd9c4165eea530ffefa78764bdaa2af61d581d2527b2e3509d3e` |
| 成本说明 | 本次 ¥0.0317（模型调用 1 次）；输入 13,177 tok / 命中 256 tok / 输出 730 tok |
| 累计 | 本周 ¥0.3851 / 208,198 tok；本月 ¥0.9724 / 318,348 tok |
| 单价 | deepseek-flash 输入未命中 ¥2/M · 缓存命中 ¥0.04/M · 输出 ¥8/M（官方中文页，核对 2026-11-03，取高峰价；低谷约为一半） |
| 口径 | 本次分析的成本（不含开发期重复调用）；账户累计见 cost；成本说明同 as-of 重跑不变（幂等优先）；两者不一致是设计，不是 bug |

**档位决策链路**：

1. L4 人工 override：--depth fast（绕过 L1 基线 / L2 配额）
2. 凭据：齐全
3. L2 周配额：人工 override 绕过（本周 strong 0/1、fast 13/5）
4. L3 预算：估算 6585 × 安全系数 1.3 = 8560 tok（单选上限 120000），周 194291/2000000
5. 结论：实际档位 fast（人工 override）

**上下文组装**（裁剪发生在调用之前）：

| 块 | 优先级 | 估算 token |
|---|---|---|
| featcard | 1 | 3,193 |
| readme | 2 | 3,392 |

- 丢弃：—
- 合计 6,585 / 上限 120,000

### B5. 特征卡摘要

- 卡文件：`data/featcards/sgl-project__sglang__e0decbc3388fbc0bf02882311df5a1aa33502018.json`（schema 1.0）
- 入口文件：python/sglang/cli/main.py, python/sglang/kernels/jit/__main__.py, python/sglang/multimodal_gen/apps/ComfyUI_SGLDiffusion/convert/__main__.py, python/sglang/multimodal_gen/apps/webui/main.py, python/sglang/multimodal_gen/runtime/entrypoints/cli/main.py, python/sglang/srt/debug_utils/comparator/__main__.py, python/sglang/srt/debug_utils/schedule_simulator/__main__.py, python/sglang/test/cuda_graph_lifetime/__main__.py, rust/sglang-api-codegen/src/main.rs, scripts/playground/disaggregation/cli.py, sgl-router/src/main.rs, sgl-router/tests/component/main.rs, sgl-router/tests/proxy/main.rs
- 最大目录深度：15；monorepo：是
- 源码切片：20 个文件（tarball `c0a6b121e2f6eb95`）
- 依赖：直接 / 传递 = — / —（L1 未解析清单文件）

**并行轴**

- 并行 `CP` = true（证据 3 条）
  - `python/sglang/srt/mem_cache/storage/mooncake_store/README.md:62` — `### Decode context parallelism (DCP)`
  - `tools/sglang-simulator/README.md:191` — `and both attention/decode context-parallel sizes set to `1`. Parallel CLI options`
  - `tools/sglang-simulator/README.md:255` — ``cp_size` is passed as AISimulate context parallelism. `cp_style` uses the`
- 并行 `DP` = true（证据 3 条）
  - `benchmark/deepseek_v3/README.md:3` — `The SGLang and DeepSeek teams collaborated to get DeepSeek V3 FP8 running on NVIDIA and AMD GPUs **from day one**. SGLan`
  - `benchmark/deepseek_v3/README.md:50` — `- [Data Parallelism Attention](https://lmsys.org/blog/2024-12-04-sglang-v0-4/#data-parallelism-attention-for-deepseek-mo`
  - `benchmark/deepseek_v3/README.md:169` — `> **Note that the launch command here does not enable Data Parallelism Attention or `torch.compile` Optimization**. For `
- 并行 `EP` = false（无证据）
- 并行 `PP` = false（无证据）
- 并行 `SP` = true（证据 3 条）
  - `python/sglang/kernels/ops/diffusion/README.md:4` — `blocks, VAE encoders/decoders, and the sequence-parallel plumbing around them.`
  - `python/sglang/multimodal_gen/apps/ComfyUI_SGLDiffusion/README.md:99` — `| cache_dit, spectrum | MiniMax H3 family (spectrum: sequence-parallel degree 1); other models send each sampler step as`
  - `python/sglang/multimodal_gen/apps/ComfyUI_SGLDiffusion/README.md:147` — `- **`flux_sgld_sp.json`**: Multi-GPU (Sequence Parallelism) workflow for FLUX models. High-performance inference across `
- 并行 `TP` = true（证据 3 条）
  - `benchmark/blog_v0_2/README.md:44` — `- 70B models: 8 x NVIDIA A100 80GB GPUs with Tensor Parallelism (TP) 8`
  - `benchmark/blog_v0_2/README.md:45` — `- 70B FP8 models: 8 x NVIDIA H100 GPUs with Tensor Parallelism (TP) 8`
  - `benchmark/deepseek_v3/README.md:180` — `python3 -m sglang.launch_server --model-path nvidia/DeepSeek-R1-0528-FP4-V2 --host 0.0.0.0 --port 8000 --tensor-parallel`

**缓存**

- 缓存 `kv_offload` = false（无证据）
- 缓存 `paged` = true（证据 1 条）
  - `python/sglang/srt/mem_cache/storage/nixl/README.md:446` — `| `use_direct_io`  | boolean | `true`   | Open cache files with `O_DIRECT` to bypass the OS page cache. Reduces memory p`
- 缓存 `prefix_reuse` = true（证据 3 条）
  - `python/sglang/srt/mem_cache/unified_cache/components/README.md:3` — `A component-based, pluggable prefix cache framework for SGLang that unifies Full-attention, Sliding-Window-Attention (SW`
  - `tools/sglang-simulator/README.md:119` — `real-SDK prefill/decode prediction and prefix reuse in SOL and SILICON modes.`
  - `tools/sglang-simulator/README.md:131` — `latency, throughput, and prefix-cache metrics.`
- 缓存 `radix` = true（证据 3 条）
  - `benchmark/blog_v0_2/README.md:30` — `python -m sglang.launch_server --model-path meta-llama/Llama-3.1-8B-Instruct --enable-torch-compile --disable-radix-cach`
  - `benchmark/blog_v0_2/README.md:33` — `python -m sglang.launch_server --model-path meta-llama/Llama-3.1-70B-Instruct --disable-radix-cache --tp 8`
  - `benchmark/blog_v0_2/README.md:36` — `python -m sglang.launch_server --model-path neuralmagic/Meta-Llama-3-70B-Instruct-FP8 --disable-radix-cache --tp 8`

- 硬件：vendors=[amd, nvidia]、arch_gates=[blackwell, hopper]、kernel_langs=[cuda, hip, tilelang, triton]
- 治理文档：是

**依赖图**（内部模块 import 边，节点/边排序后输出）

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

**已知限制**：

- 证据来自 20 个源码切片的逐行扫描，未覆盖文件不计入
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B6. 体检事实（确定性，零 LLM）

| 指标 | 值 |
|---|---|
| Star / Fork | 39,021 / 10,590 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 447 / 7.34% |
| Top10 贡献集中度 | 40.55% |
| 90 天 / 365 天提交 | 2,000 / 2,000 |
| 最近提交 / 距今天数 | 2026-11-18T11:20:39Z / 0 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 1,045 天 / 25 |
| 组织类型 / 许可证 | — / Apache-2.0 |
| 文件数 / 体积 | 12,388 / 166.0 MiB |
| 内部模块依赖边 | 0 |

**语言构成**：Assembly 0.03%、C 0.10%、C++ 1.42%、CMake 0.02%、CSS 0.01%、Cuda 4.51%、Dockerfile 0.13%、Go Template 0.03%、HIP 0.06%、HTML 0.01%、JavaScript 0.09%、Jinja 0.03%、Jupyter Notebook 0.01%、Makefile 0.00%、Metal 0.02%、Python 86.35%、Rust 6.74%、Shell 0.39%、Vim Script 0.00%、mupad 0.07%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| python | 6,734 | 90,679,028 |
| test | 3,445 | 36,077,114 |
| docs | 692 | 21,782,819 |
| rust | 308 | 9,134,699 |
| sgl-router | 292 | 5,757,368 |
| assets | 25 | 2,293,786 |
| scripts | 207 | 1,926,100 |
| benchmark | 150 | 1,645,494 |
| .agents | 112 | 1,536,969 |
| .github | 153 | 1,386,697 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算
