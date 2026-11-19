# 开源项目分析 · microsoft/onnxruntime

## 运行元数据

| 项 | 值 |
|---|---|
| 仓库 | microsoft/onnxruntime |
| commit | `fd249b559c4829ddf3c388d621174a098f9e41ee` |
| 分析基准时间 (as-of) | 2026-11-13T14:56:59Z |
| 通道 / 领域 | classic / 未指定 |
| 请求档位 (requested_depth) | fast |
| **实际档位** (actual_depth) | off（降级：未配置 LLM 凭据（api_key / base_url / model 缺一）） |
| 降级原因 (reason) | no_credentials — 未配置 LLM 凭据（api_key / base_url / model 缺一） |
| 配额状态 (quota_state) | strong 0/1、fast 0/3（周起点 2026-11-09）；tokens 周 0/2000000、月 97234/6000000（月起点 2026-11-01） |
| 快照 sha256 | `a820b6008e6bda586dd68956b44f59d0844173981281f1423bf045a42565df4e` |
| 成本说明 | 本次 —（未调用）；输入 0 tok / 命中 0 tok / 输出 0 tok |
| 累计 | 本周 ¥0.0000 / 0 tok；本月 ¥0.5595 / 97,234 tok |
| 单价 | deepseek-flash 输入未命中 ¥2/M · 缓存命中 ¥0.04/M · 输出 ¥8/M（官方中文页，核对 2026-11-03，取高峰价；低谷约为一半） |
| 口径 | 本次分析的成本（不含开发期重复调用）；账户累计见 cost；成本说明同 as-of 重跑不变（幂等优先）；两者不一致是设计，不是 bug |

**档位决策链路**：

1. L1 通道基线：classic → strong；自动链按 auto_default=fast 取更省档位 → fast（非 L4 人工 override）
2. 凭据：api_key / base_url / model 缺一 → 降级 off（退出码仍为 0）

**上下文组装**（裁剪发生在调用之前）：

| 块 | 优先级 | 估算 token |
|---|---|---|
| featcard | 1 | — |
| readme | 2 | — |
| source_files | 4 | — |

- 丢弃：—（off 档不组装上下文，未发起任何模型请求）
- 合计 0 / 上限 120000

## 体检事实（确定性，零 LLM）

| 指标 | 值 |
|---|---|
| Star / Fork | 22,299 / 4,443 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 403 / 5.98% |
| Top10 贡献集中度 | 32.92% |
| 90 天 / 365 天提交 | 964 / 2,000 |
| 最近提交 / 距今天数 | 2026-11-13T06:06:01Z / 0 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 2,925 天 / 28 |
| 组织类型 / 许可证 | — / MIT |
| 文件数 / 体积 | 11,682 / 566.9 MiB |
| 内部模块依赖边 | 0 |

**语言构成**：Assembly 1.67%、Batchfile 0.01%、C 3.16%、C# 1.41%、C++ 82.22%、CMake 0.41%、CSS 0.06%、Cuda 2.81%、Dockerfile 0.01%、Go 0.07%、Go Template 0.00%、HIP 0.00%、HLSL 0.01%、HTML 0.01%、Java 0.29%、JavaScript 0.45%、Jupyter Notebook 0.10%、Just 0.00%、Kotlin 0.00%、Linker Script 0.00%、Liquid 0.00%、NASL 0.00%、Objective-C 0.11%、Objective-C++ 0.08%、Pascal 0.00%、PowerShell 0.02%、Puppet 0.00%、Python 5.95%、Ruby 0.00%、Rust 0.12%、Shell 0.07%、Swift 0.00%、TypeScript 0.93%、Vue 0.00%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| onnxruntime | 7,797 | 428,241,693 |
| winml | 341 | 102,082,049 |
| csharp | 388 | 17,524,685 |
| js | 729 | 16,322,408 |
| docs | 154 | 7,315,852 |
| orttraining | 815 | 7,258,493 |
| cmake | 201 | 4,991,382 |
| tools | 587 | 2,872,909 |
| java | 134 | 2,387,728 |
| include | 148 | 2,103,830 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算

## 特征卡摘要

- 卡文件：`data/featcards/microsoft__onnxruntime__fd249b559c4829ddf3c388d621174a098f9e41ee.json`（schema 1.0）
- 入口文件：csharp/test/Microsoft.AI.MachineLearning.Tests/main.cpp, js/common/lib/index.ts, js/node/lib/index.ts, js/node/src/main.cc, js/node/test/standalone/index.ts, js/node/test/unittests/lib/index.ts, js/react_native/lib/index.ts, js/web/lib/index.ts, js/web/test/e2e/type/testcases/module-resolution/index.ts, js/web/test/unittests/index.ts, onnxruntime/test/ep_weight_sharing_ctx_gen/main.cc, onnxruntime/test/onnx/main.cc, onnxruntime/test/onnx/microbenchmark/main.cc, onnxruntime/test/perftest/main.cc, onnxruntime/test/webgpu/delay_load/main.cc, onnxruntime/test/webgpu/external_dawn/main.cc, onnxruntime/tool/etw/main.cc, orttraining/orttraining/models/bert/main.cc, orttraining/orttraining/models/gpt2/main.cc, orttraining/orttraining/models/mnist/main.cc, orttraining/orttraining/models/pipeline_poc/main.cc, orttraining/orttraining/models/squeezenet/main.cc, samples/cxx/main.cc, samples/nodejs/01_basic-usage/index.js, samples/nodejs/02_create-tensor/index.js, samples/nodejs/04_create-inference-session/index.js, winml/test/common/googletest/main.cpp
- 最大目录深度：13；monorepo：是
- 源码切片：20 个文件（tarball `caa8a82b354b9913`）
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

- 硬件：vendors=[amd, nvidia]、arch_gates=[]、kernel_langs=[cuda]
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

## 洞见

—

## 外部资料

- 来源：deepwiki
- url：https://deepwiki.com/microsoft/onnxruntime
- fetched_at：2026-11-13T14:59:07Z
- sha256：`0110e47af243b382ea940959b93860616d5cfda4830bc7a0e8d5eb711ff1fb03`
- 判定：hit — 正文含 5 个仓库内真实路径（阈值 3）
- 原文快照：`source.txt`（与判定元数据分文件存放）
