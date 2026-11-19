# 开源项目分析 · huggingface/text-generation-inference

## 运行元数据

| 项 | 值 |
|---|---|
| 仓库 | huggingface/text-generation-inference |
| commit | `b4adbf2f6e2e721280bd0ea5f91d70f7d033f5ed` |
| 分析基准时间 (as-of) | 2026-11-06T00:00:00Z |
| 通道 / 领域 | classic / 未指定 |
| 请求档位 (requested_depth) | off |
| **实际档位** (actual_depth) | off |
| 降级原因 (reason) | explicit_off — 显式请求 off 档（零 LLM） |
| 配额状态 (quota_state) | strong 1/1、fast 3/3（周起点 2026-11-02）；tokens 周 97234/2000000、月 97234/6000000（月起点 2026-11-01） |
| 快照 sha256 | `75d9c6775ec82f12f6ae78ca01091e271ef036c0370b8bad338fc2c5e1c8bb49` |
| 成本说明 | 本次 —（未调用）；输入 0 tok / 命中 0 tok / 输出 0 tok |
| 累计 | 本周 ¥0.5595 / 97,234 tok；本月 ¥0.5595 / 97,234 tok |
| 单价 | deepseek-flash 输入未命中 ¥2/M · 缓存命中 ¥0.04/M · 输出 ¥8/M（官方中文页，核对 2026-11-03，取高峰价；低谷约为一半） |
| 口径 | 本次分析的成本（不含开发期重复调用）；账户累计见 cost；成本说明同 as-of 重跑不变（幂等优先）；两者不一致是设计，不是 bug |

**档位决策链路**：

1. L4 人工 override：显式 --depth off（不再评估其它层）

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
| Star / Fork | 10,882 / 1,287 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 145 / 25.29% |
| Top10 贡献集中度 | 81.64% |
| 90 天 / 365 天提交 | 0 / 8 |
| 最近提交 / 距今天数 | 2026-03-21T11:34:22Z / 230 |
| 维护状态 | archived |
| 项目年龄 / 发布数(365d) | 1,490 天 / 1 |
| 组织类型 / 许可证 | — / Apache-2.0 |
| 文件数 / 体积 | 878 / 9.3 MiB |
| 内部模块依赖边 | 0 |

**语言构成**：C 0.02%、C++ 0.85%、CMake 0.17%、Cuda 2.90%、Dockerfile 0.18%、JavaScript 0.12%、Makefile 0.23%、Nix 0.31%、Python 78.72%、Rust 16.26%、Shell 0.25%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| server | 215 | 2,846,263 |
| backends | 216 | 2,099,489 |
| integration-tests | 287 | 1,973,116 |
| assets | 4 | 1,371,571 |
| router | 16 | 380,653 |
| . | 26 | 290,762 |
| docs | 46 | 268,165 |
| clients | 15 | 235,639 |
| launcher | 5 | 89,520 |
| load_tests | 10 | 68,876 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算

## 特征卡摘要

- 卡文件：`data/featcards/huggingface__text-generation-inference__b4adbf2f6e2e721280bd0ea5f91d70f7d033f5ed.json`（schema 1.0）
- 入口文件：backends/gaudi/server/text_generation_server/cli.py, backends/llamacpp/src/main.rs, backends/neuron/server/text_generation_server/cli.py, backends/trtllm/src/main.rs, backends/v2/src/main.rs, backends/v3/src/main.rs, benchmark/src/main.rs, launcher/src/main.rs, server/text_generation_server/cli.py
- 最大目录深度：8；monorepo：是
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

## 洞见

—

## 外部资料

- 来源：deepwiki
- url：https://deepwiki.com/huggingface/text-generation-inference
- fetched_at：2026-11-06T15:49:20Z
- sha256：`115e02faeb7bfbae17abfaca5dc49ff21aac8ff51432801670bbc9277eff72c6`
- 判定：hit — 正文含 185 个仓库内真实路径（阈值 3）
- 原文快照：`source.txt`（与判定元数据分文件存放）
