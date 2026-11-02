# 开源项目分析 · deepseek-ai/DeepEP

## 运行元数据

| 项 | 值 |
|---|---|
| 仓库 | deepseek-ai/DeepEP |
| commit | `f6aa38fe06cd4a0489e7730365d4e0114970a2f3` |
| 分析基准时间 (as-of) | 2026-11-02T00:00:00Z |
| 通道 / 领域 | classic / 未指定 |
| 请求档位 (requested_depth) | auto |
| **实际档位** (actual_depth) | off（降级：未配置 LLM 凭据（api_key / base_url / model 缺一）） |
| 降级原因 (reason) | no_credentials — 未配置 LLM 凭据（api_key / base_url / model 缺一） |
| 配额状态 (quota_state) | strong 0/1、fast 0/3（周起点 2026-11-02）；tokens 周 0/2000000、月 0/6000000（月起点 2026-11-01） |
| 快照 sha256 | `4ba889ed2da18b8274f3b110eee43dcf5cff2e054898590810f8243e4e09e748` |

**档位决策链路**：

1. L1 通道基线：classic → strong
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
| Star / Fork | 10,403 / 1,535 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 50 / 36.33% |
| Top10 贡献集中度 | 82.03% |
| 90 天 / 365 天提交 | 7 / 27 |
| 最近提交 / 距今天数 | 2026-10-21T03:50:43Z / 12 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 623 天 / 0 |
| 组织类型 / 许可证 | — / MIT |
| 文件数 / 体积 | 126 / 2.0 MiB |
| 内部模块依赖边 | — |

**语言构成**：C++ 24.11%、CMake 0.28%、Cuda 41.56%、Python 33.92%、Shell 0.13%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| figures | 2 | 1,206,548 |
| deep_ep | 62 | 496,996 |
| csrc | 36 | 208,921 |
| tests | 14 | 144,883 |
| . | 10 | 43,576 |
| third-party | 2 | 5,105 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算

## 特征卡摘要

- 卡文件：`data/featcards/deepseek-ai__DeepEP__f6aa38fe06cd4a0489e7730365d4e0114970a2f3.json`（schema 1.0）
- 入口文件：csrc/indexing/main.cu
- 最大目录深度：7；monorepo：否
- 依赖：直接 / 传递 = — / —（L0 未解析清单文件）
- 并行轴 hits：CP=False、DP=False、EP=False、PP=False、SP=False、TP=False
- 缓存 hits：kv_offload=False、paged=False、prefix_reuse=False、radix=False
- 硬件：vendors=[]、arch_gates=[]、kernel_langs=[]
- 治理文档：否

**已知限制**（L0 只跑元数据层，逐条可核验）：

- L0 只跑元数据层：未读取源码内容，parallel/cache/hardware 全部 false，deps.* 与 loc_total 为 null（红线 #5：无证据不写入）
- issue_close_ratio_90d 需 search API，L0 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，L0 置 null

## 洞见

—

## 外部资料

- DeepWiki / Zread：不可用（未索引）
- 判定原因：L0 未接线外部工具（L1 起启用 fail-closed 判定），本次未发起任何探测请求；快照 sha256 `4ba889ed2da18b8274f3b110eee43dcf5cff2e054898590810f8243e4e09e748`
