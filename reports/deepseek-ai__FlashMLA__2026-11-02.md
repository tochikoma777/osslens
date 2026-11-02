# 开源项目分析 · deepseek-ai/FlashMLA

## 运行元数据

| 项 | 值 |
|---|---|
| 仓库 | deepseek-ai/FlashMLA |
| commit | `395cb3afbb331fef7b1b21e9340861b9436b42d8` |
| 分析基准时间 (as-of) | 2026-11-02T00:00:00Z |
| 通道 / 领域 | hot / 未指定 |
| 请求档位 (requested_depth) | auto |
| **实际档位** (actual_depth) | off（降级：未配置 LLM 凭据（api_key / base_url / model 缺一）） |
| 降级原因 (reason) | no_credentials — 未配置 LLM 凭据（api_key / base_url / model 缺一） |
| 配额状态 (quota_state) | strong 0/1、fast 0/3（周起点 2026-11-02）；tokens 周 0/2000000、月 0/6000000（月起点 2026-11-01） |
| 快照 sha256 | `9ebe8e5a29427befaa2eaad04602a2af1912aa761ec1f34203e1d3be057ff51a` |

**档位决策链路**：

1. L1 通道基线：hot → fast
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
| Star / Fork | 13,234 / 1,256 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 19 / 36.51% |
| Top10 贡献集中度 | 85.71% |
| 90 天 / 365 天提交 | 6 / 13 |
| 最近提交 / 距今天数 | 2026-10-27T02:50:39Z / 6 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 619 天 / 0 |
| 组织类型 / 许可证 | — / MIT |
| 文件数 / 体积 | 150 / 1.4 MiB |
| 内部模块依赖边 | — |

**语言构成**：AGS Script 0.16%、C 0.23%、C++ 55.44%、Cuda 28.48%、Python 15.68%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| csrc | 119 | 1,106,463 |
| docs | 5 | 125,581 |
| tests | 17 | 125,580 |
| . | 5 | 40,662 |
| flash_mla | 3 | 38,431 |
| scripts | 1 | 2,468 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算

## 特征卡摘要

- 卡文件：`data/featcards/deepseek-ai__FlashMLA__395cb3afbb331fef7b1b21e9340861b9436b42d8.json`（schema 1.0）
- 入口文件：—
- 最大目录深度：9；monorepo：否
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
- 判定原因：L0 未接线外部工具（L1 起启用 fail-closed 判定），本次未发起任何探测请求；快照 sha256 `9ebe8e5a29427befaa2eaad04602a2af1912aa761ec1f34203e1d3be057ff51a`
