# microsoft/onnxruntime 深度分析

> 阅读档位：架构学习（profile=architecture_learning）
> 注意力预算：定位 20 / 架构 30 / 抽象 15 / ADR 20 / 扩展 5 / 经验卡 10 / 工程维护 0
> 证据约定：[事实] 确定性提取 · [判断] 有 file:line 或文档锚点 · [未获得] 当前未采集

## 导读

> **是什么**：ONNX Runtime: cross-platform, high performance ML inferencing and training accelerator
> **架构一句话**：[判断] 顶层以 `onnxruntime`、`winml`、`js` 为主，入口为 `csharp/test/Microsoft.AI.MachineLearning.Tests/main.cpp`（静态结构判断，未做动态跟踪）。
> **最大风险**：Top1 贡献者占比 5.99%，决策集中度需关注
> **不适合**：需要稳定 API/长期支持承诺的场景，请先核对发布节奏与维护状态；依赖链许可证与权重许可能力当前未采集，不能据此做出商用结论。

## 1. 项目定位与目标

[事实] microsoft/onnxruntime 属于 `未指定` 领域、`classic` 通道，主语言 C++（82%），22,334 stars / 4,460 forks。

[事实] 项目自述：ONNX Runtime: cross-platform, high performance ML inferencing and training accelerator。

[事实] README 摘要：[未获得] 本次未获得可用 README 文本。

- **目标用户**：[判断] 应用与平台开发者
- **替代方案与差异**：[未获得] 本次未采集竞品对比与 roadmap，不得据此推断「没有替代品」。
- **不解决什么**：[未获得] 没有路线图与 issue 语料，无法可靠界定能力边界。

[判断] 阶段信号：仓库已存在 2,929 天，近一年发布 30 个版本，最近提交距今 0 天，维护状态「active」。这只说明是否仍在维护，不等于成熟度结论。

## 2. 架构全景

### 2.1 上下文边界

[判断] 架构说明文档：[未获得]；边界结论来自文档与目录结构，未经运行验证。
[事实] 硬件/内核线索：vendors=[]、kernel_langs=[]。

### 2.2 模块职责

| 模块 | 文件数 | 职责（启发式） |
|---|---:|---|
| `onnxruntime` | 7,815 | 业务实现（职责需人工确认） |
| `winml` | 341 | 业务实现（职责需人工确认） |
| `js` | 730 | 业务实现（职责需人工确认） |
| `csharp` | 319 | 业务实现（职责需人工确认） |
| `docs` | 154 | 文档 |

### 2.3 一次调用的路径（运行时视图）

[判断] 静态推断：`csharp/test/Microsoft.AI.MachineLearning.Tests/main.cpp`, `js/common/lib/index.ts`, `js/node/lib/index.ts`, `js/node/src/main.cc`, `js/node/test/standalone/index.ts`, `js/node/test/unittests/lib/index.ts`, `js/react_native/lib/index.ts`, `js/web/lib/index.ts`, `js/web/test/e2e/type/testcases/module-resolution/index.ts`, `js/web/test/unittests/index.ts`, `onnxruntime/test/ep_weight_sharing_ctx_gen/main.cc`, `onnxruntime/test/onnx/main.cc`, `onnxruntime/test/onnx/microbenchmark/main.cc`, `onnxruntime/test/perftest/main.cc`, `onnxruntime/test/webgpu/delay_load/main.cc`, `onnxruntime/test/webgpu/external_dawn/main.cc`, `onnxruntime/tool/etw/main.cc`, `orttraining/orttraining/models/bert/main.cc`, `orttraining/orttraining/models/gpt2/main.cc`, `orttraining/orttraining/models/mnist/main.cc`, `orttraining/orttraining/models/pipeline_poc/main.cc`, `orttraining/orttraining/models/squeezenet/main.cc`, `samples/cxx/main.cc`, `samples/nodejs/01_basic-usage/index.js`, `samples/nodejs/02_create-tensor/index.js`, `samples/nodejs/04_create-inference-session/index.js`, `winml/test/common/googletest/main.cpp` → 输出。内部 import 边约 0 条，只用于判断调用方向；**未做运行时跟踪**，参数与分支需读源码确认。

### 2.4 数据与控制流

[未获得] 未检测到并行/缓存轴证据；不代表项目中不存在。

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

## 3. 核心抽象与契约

[未获得] 本次源码切片未识别到显式接口/注册模式；这不等于项目没有抽象层，只说明当前采集粒度不足。

入口候选（可作为契约阅读起点）：`csharp/test/Microsoft.AI.MachineLearning.Tests/main.cpp`、`js/common/lib/index.ts`、`js/node/lib/index.ts`、`js/node/src/main.cc`、`js/node/test/standalone/index.ts`、`js/node/test/unittests/lib/index.ts`、`js/react_native/lib/index.ts`、`js/web/lib/index.ts`、`js/web/test/e2e/type/testcases/module-resolution/index.ts`、`js/web/test/unittests/index.ts`、`onnxruntime/test/ep_weight_sharing_ctx_gen/main.cc`、`onnxruntime/test/onnx/main.cc`、`onnxruntime/test/onnx/microbenchmark/main.cc`、`onnxruntime/test/perftest/main.cc`、`onnxruntime/test/webgpu/delay_load/main.cc`、`onnxruntime/test/webgpu/external_dawn/main.cc`、`onnxruntime/tool/etw/main.cc`、`orttraining/orttraining/models/bert/main.cc`、`orttraining/orttraining/models/gpt2/main.cc`、`orttraining/orttraining/models/mnist/main.cc`、`orttraining/orttraining/models/pipeline_poc/main.cc`、`orttraining/orttraining/models/squeezenet/main.cc`、`samples/cxx/main.cc`、`samples/nodejs/01_basic-usage/index.js`、`samples/nodejs/02_create-tensor/index.js`、`samples/nodejs/04_create-inference-session/index.js`、`winml/test/common/googletest/main.cpp`

## 4. 关键设计决策（ADR）

[未获得] 判废：空输出或输出顶格；ADR 至少 3 条的要求未满足，不用通用判断填充。

## 5. 扩展与改造路径

[未获得] 未识别到显式插件/注册点。

[判断] 新增能力的静态路径（需按实际代码复核）：

1. 在入口处接入参数/配置（入口候选：`csharp/test/Microsoft.AI.MachineLearning.Tests/main.cpp`, `js/common/lib/index.ts`, `js/node/lib/index.ts`, `js/node/src/main.cc`, `js/node/test/standalone/index.ts`, `js/node/test/unittests/lib/index.ts`, `js/react_native/lib/index.ts`, `js/web/lib/index.ts`, `js/web/test/e2e/type/testcases/module-resolution/index.ts`, `js/web/test/unittests/index.ts`, `onnxruntime/test/ep_weight_sharing_ctx_gen/main.cc`, `onnxruntime/test/onnx/main.cc`, `onnxruntime/test/onnx/microbenchmark/main.cc`, `onnxruntime/test/perftest/main.cc`, `onnxruntime/test/webgpu/delay_load/main.cc`, `onnxruntime/test/webgpu/external_dawn/main.cc`, `onnxruntime/tool/etw/main.cc`, `orttraining/orttraining/models/bert/main.cc`, `orttraining/orttraining/models/gpt2/main.cc`, `orttraining/orttraining/models/mnist/main.cc`, `orttraining/orttraining/models/pipeline_poc/main.cc`, `orttraining/orttraining/models/squeezenet/main.cc`, `samples/cxx/main.cc`, `samples/nodejs/01_basic-usage/index.js`, `samples/nodejs/02_create-tensor/index.js`, `samples/nodejs/04_create-inference-session/index.js`, `winml/test/common/googletest/main.cpp`）；
2. 复用上表中的注册/分派结构，实现新的后端或适配器；
3. 补对应测试与文档，再走发布流程。

- 扩展文档：[未获得]
- 改造成本：[未获得] 需要先确认契约稳定性与测试覆盖，本报告不估算人日。

## 6. 经验卡

[未获得] 本次没有带「可迁移规则」的条目（模型未输出 rule，或命中旧缓存）；经验卡留空，不用「要注重解耦」这类通用建议充数。

## 附录 A 证据索引与未知项

### A1. 代码证据索引

—

> 未产出洞见：判废：空输出或输出顶格

### A2. 外部资料

- 来源：deepwiki
- url：https://deepwiki.com/microsoft/onnxruntime
- fetched_at：2026-11-19T15:04:43Z
- sha256：`0110e47af243b382ea940959b93860616d5cfda4830bc7a0e8d5eb711ff1fb03`
- 判定：hit — 正文含 2577 个仓库内真实路径（阈值 3）
- 原文快照：`source.txt`（与判定元数据分文件存放）

### A3. 未获得项

- 依赖链许可证、模型权重/数据许可、CLA —— 未采集；
- issue/PR 响应质量、CI 运行结果 —— 未采集；
- roadmap、竞品对比、用户画像 —— 未采集；
**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算


## 附录 B 许可证 / 维护 / 工程 / 成本

### B1. 许可证与合规风险

[事实] 主许可证 **MIT**；组织类型 —；治理文档：有。

[未获得] 依赖链是否存在 GPL/AGPL、模型权重与数据集许可、CLA 要求；这些必须人工或由后续数据源补齐，本报告不给出「可商用」结论。

### B2. 维护状态与风险

[事实] 贡献者 403 人，Top1 占比 5.99%；近 90 天 / 365 天提交 979 / 2,000 次；最近提交距今 0 天，维护状态「active」。

- Top1 贡献者占比 5.99%，决策集中度需关注

### B3. 运行与工程体系

[事实] 仓库约 11,637 个文件、566.4 MiB；本次采集 0 个源码切片（tarball `—`）。
[事实] 语言构成：Assembly 1.66%、Batchfile 0.01%、C 3.15%、C# 1.40%、C++ 82.30%、CMake 0.41%、CSS 0.00%、Cuda 2.85%、Dockerfile 0.01%、Go 0.07%、HIP 0.00%、HLSL 0.01%、HTML 0.01%、Java 0.29%、JavaScript 0.37%、Jupyter Notebook 0.10%、Just 0.00%、Kotlin 0.00%、Linker Script 0.00%、NASL 0.00%、Objective-C 0.11%、Objective-C++ 0.08%、Pascal 0.00%、PowerShell 0.02%、Puppet 0.00%、Python 6.00%、Ruby 0.00%、Rust 0.12%、Shell 0.07%、Swift 0.00%、TypeScript 0.93%、Vue 0.00%；硬件 vendors=[]、kernel_langs=[]。

[未获得] 构建脚本、依赖安装、测试体系、CI/CD、配置与 secret 管理未采集；本报告不能回答「能否在目标环境跑起来」。

**特征卡已知限制**：

- 未取得源码切片：parallel/cache/hardware 全部 false、deps.graph 为空（红线 #5）
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B4. 运行元数据与成本

| 项 | 值 |
|---|---|
| 仓库 | microsoft/onnxruntime |
| commit | `5e289356eff2c1c66e83696a7b119f388230d5af` |
| 分析基准时间 (as-of) | 2026-11-17T00:00:00Z |
| 通道 / 领域 | classic / 未指定 |
| 请求档位 (requested_depth) | fast |
| **实际档位** (actual_depth) | fast |
| 降级原因 (reason) | manual_override — 人工 override |
| 配额状态 (quota_state) | strong 0/1、fast 15/5（周起点 2026-11-16）；tokens 周 220299/2000000、月 330449/6000000（月起点 2026-11-01） |
| 快照 sha256 | `870a024404e74590a438994a1d7687f5007d83cc19e7cd70e6f801447d4de1f2` |
| 成本说明 | 本次 ¥0.0000（模型调用 0 次）；输入 0 tok / 命中 0 tok / 输出 0 tok |
| 累计 | 本周 ¥0.4141 / 220,299 tok；本月 ¥1.0014 / 330,449 tok |
| 单价 | deepseek-flash 输入未命中 ¥2/M · 缓存命中 ¥0.04/M · 输出 ¥8/M（官方中文页，核对 2026-11-03，取高峰价；低谷约为一半） |
| 口径 | 本次分析的成本（不含开发期重复调用）；账户累计见 cost；成本说明同 as-of 重跑不变（幂等优先）；两者不一致是设计，不是 bug |

**档位决策链路**：

1. L4 人工 override：--depth fast（绕过 L1 基线 / L2 配额）
2. 凭据：齐全
3. L2 周配额：人工 override 绕过（本周 strong 0/1、fast 15/5）
4. L3 预算：估算 1454 × 安全系数 1.3 = 1890 tok（单选上限 120000），周 220299/2000000
5. 结论：实际档位 fast（人工 override）

**上下文组装**（裁剪发生在调用之前）：

| 块 | 优先级 | 估算 token |
|---|---|---|
| featcard | 1 | 1,454 |

- 丢弃：—
- 合计 1,454 / 上限 120,000

### B5. 特征卡摘要

- 卡文件：`data/featcards/microsoft__onnxruntime__5e289356eff2c1c66e83696a7b119f388230d5af.json`（schema 1.0）
- 入口文件：csharp/test/Microsoft.AI.MachineLearning.Tests/main.cpp, js/common/lib/index.ts, js/node/lib/index.ts, js/node/src/main.cc, js/node/test/standalone/index.ts, js/node/test/unittests/lib/index.ts, js/react_native/lib/index.ts, js/web/lib/index.ts, js/web/test/e2e/type/testcases/module-resolution/index.ts, js/web/test/unittests/index.ts, onnxruntime/test/ep_weight_sharing_ctx_gen/main.cc, onnxruntime/test/onnx/main.cc, onnxruntime/test/onnx/microbenchmark/main.cc, onnxruntime/test/perftest/main.cc, onnxruntime/test/webgpu/delay_load/main.cc, onnxruntime/test/webgpu/external_dawn/main.cc, onnxruntime/tool/etw/main.cc, orttraining/orttraining/models/bert/main.cc, orttraining/orttraining/models/gpt2/main.cc, orttraining/orttraining/models/mnist/main.cc, orttraining/orttraining/models/pipeline_poc/main.cc, orttraining/orttraining/models/squeezenet/main.cc, samples/cxx/main.cc, samples/nodejs/01_basic-usage/index.js, samples/nodejs/02_create-tensor/index.js, samples/nodejs/04_create-inference-session/index.js, winml/test/common/googletest/main.cpp
- 最大目录深度：13；monorepo：是
- 源码切片：0 个文件（tarball ``）
- 依赖：直接 / 传递 = — / —（L1 未解析清单文件）

**并行轴**

- 并行 `CP` = false（无证据）
- 并行 `DP` = false（无证据）
- 并行 `EP` = false（无证据）
- 并行 `PP` = false（无证据）
- 并行 `SP` = false（无证据）
- 并行 `TP` = false（无证据）

**缓存**

- 缓存 `kv_offload` = false（无证据）
- 缓存 `paged` = false（无证据）
- 缓存 `prefix_reuse` = false（无证据）
- 缓存 `radix` = false（无证据）

- 硬件：vendors=[]、arch_gates=[]、kernel_langs=[]
- 治理文档：是

**依赖图**（内部模块 import 边，节点/边排序后输出）

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

**已知限制**：

- 未取得源码切片：parallel/cache/hardware 全部 false、deps.graph 为空（红线 #5）
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B6. 体检事实（确定性，零 LLM）

| 指标 | 值 |
|---|---|
| Star / Fork | 22,334 / 4,460 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 403 / 5.99% |
| Top10 贡献集中度 | 32.90% |
| 90 天 / 365 天提交 | 979 / 2,000 |
| 最近提交 / 距今天数 | 2026-11-17T04:59:41Z / 0 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 2,929 天 / 30 |
| 组织类型 / 许可证 | — / MIT |
| 文件数 / 体积 | 11,637 / 566.4 MiB |
| 内部模块依赖边 | 0 |

**语言构成**：Assembly 1.66%、Batchfile 0.01%、C 3.15%、C# 1.40%、C++ 82.30%、CMake 0.41%、CSS 0.00%、Cuda 2.85%、Dockerfile 0.01%、Go 0.07%、HIP 0.00%、HLSL 0.01%、HTML 0.01%、Java 0.29%、JavaScript 0.37%、Jupyter Notebook 0.10%、Just 0.00%、Kotlin 0.00%、Linker Script 0.00%、NASL 0.00%、Objective-C 0.11%、Objective-C++ 0.08%、Pascal 0.00%、PowerShell 0.02%、Puppet 0.00%、Python 6.00%、Ruby 0.00%、Rust 0.12%、Shell 0.07%、Swift 0.00%、TypeScript 0.93%、Vue 0.00%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| onnxruntime | 7,815 | 428,944,218 |
| winml | 341 | 102,082,049 |
| js | 730 | 16,330,261 |
| csharp | 319 | 16,228,645 |
| docs | 154 | 7,324,155 |
| orttraining | 815 | 7,258,493 |
| cmake | 201 | 4,992,518 |
| tools | 590 | 2,899,916 |
| java | 134 | 2,387,728 |
| include | 148 | 2,110,795 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算
