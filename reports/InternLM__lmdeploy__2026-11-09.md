# 开源项目分析 · InternLM/lmdeploy

## 运行元数据

| 项 | 值 |
|---|---|
| 仓库 | InternLM/lmdeploy |
| commit | `a0102d47967df04047c404278f423ee544d41868` |
| 分析基准时间 (as-of) | 2026-11-09T00:00:00Z |
| 通道 / 领域 | classic / 未指定 |
| 请求档位 (requested_depth) | off |
| **实际档位** (actual_depth) | off |
| 降级原因 (reason) | explicit_off — 显式请求 off 档（零 LLM） |
| 配额状态 (quota_state) | strong 0/1、fast 0/3（周起点 2026-11-09）；tokens 周 0/2000000、月 97234/6000000（月起点 2026-11-01） |
| 快照 sha256 | `179af549e81b55ad56b952c4f30d05e8b7be14cf2d0c3ebd6b377d5ee5c05292` |
| 成本说明 | 本次 —（未调用）；输入 0 tok / 命中 0 tok / 输出 0 tok |
| 累计 | 本周 ¥0.0000 / 0 tok；本月 ¥0.5595 / 97,234 tok |
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
| Star / Fork | 8,136 / 774 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 162 / 19.39% |
| Top10 贡献集中度 | 78.40% |
| 90 天 / 365 天提交 | 150 / 591 |
| 最近提交 / 距今天数 | 2026-11-06T11:25:02Z / 3 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 1,243 天 / 14 |
| 组织类型 / 许可证 | — / Apache-2.0 |
| 文件数 / 体积 | 2,005 / 16.6 MiB |
| 内部模块依赖边 | 0 |

**语言构成**：C 0.01%、C++ 18.26%、CMake 0.40%、Cuda 8.73%、Dockerfile 0.03%、Jinja 0.15%、PowerShell 0.03%、Python 72.26%、Shell 0.13%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| lmdeploy | 759 | 7,039,828 |
| src | 562 | 4,434,362 |
| tests | 279 | 3,454,654 |
| autotest | 155 | 1,020,125 |
| docs | 139 | 737,459 |
| benchmark | 13 | 237,882 |
| .github | 26 | 162,529 |
| . | 21 | 104,439 |
| resources | 1 | 41,480 |
| scripts | 3 | 34,791 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算

## 特征卡摘要

- 卡文件：`data/featcards/InternLM__lmdeploy__a0102d47967df04047c404278f423ee544d41868.json`（schema 1.0）
- 入口文件：lmdeploy/__main__.py, lmdeploy/cli/cli.py
- 最大目录深度：7；monorepo：否
- 源码切片：20 个文件（tarball `7334309f2b48321b`）
- 依赖：直接 / 传递 = — / —（L1 未解析清单文件）

**并行轴**

- 并行 `CP` = true（证据 2 条）
  - `autotest/configs/README.md:236` — `## Context parallel (`cp`)`
  - `src/turbomind/engine/README.md:56` — ``cache_block_seq_len` is the physical number of rank-local tokens stored in one KV cache object. With context-parallel s`
- 并行 `DP` = false（无证据）
- 并行 `EP` = false（无证据）
- 并行 `PP` = false（无证据）
- 并行 `SP` = false（无证据）
- 并行 `TP` = true（证据 3 条）
  - `README.md:87` — `- \[2023/07\] TurboMind supports tensor-parallel inference of InternLM.`
  - `README.md:97` — `- **Efficient Inference**: LMDeploy delivers up to 1.8x higher request throughput than vLLM, by introducing key features`
  - `README_zh-CN.md:86` — `- \[2023/07\] TurboMind 支持 InternLM 的 Tensor Parallel 推理`

**缓存**

- 缓存 `kv_offload` = false（无证据）
- 缓存 `paged` = true（证据 3 条）
  - `lmdeploy/pytorch/backends/cuda/attention/__init__.py:7` — `from lmdeploy.pytorch.backends.attention import PagedAttentionBuildSpec`
  - `lmdeploy/pytorch/backends/cuda/attention/__init__.py:87` — `def _build_paged_attention(spec: PagedAttentionBuildSpec) -> TritonAttentionImpl:`
  - `lmdeploy/pytorch/backends/cuda/attention/__init__.py:88` — `"""Build the selected CUDA paged-attention implementation.`
- 缓存 `prefix_reuse` = true（证据 3 条）
  - `lmdeploy/cli/cli.py:57` — `ArgumentHelper.prefix_cache_state_budget(pt_group)`
  - `lmdeploy/cli/cli.py:58` — `ArgumentHelper.prefix_cache_decode_state_interval(pt_group)`
  - `lmdeploy/cli/cli.py:59` — `ArgumentHelper.prefix_cache_decode_save_first(pt_group)`
- 缓存 `radix` = false（无证据）

- 硬件：vendors=[ascend, nvidia]、arch_gates=[ampere]、kernel_langs=[cuda, tilelang, triton]
- 治理文档：否

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
- url：https://deepwiki.com/InternLM/lmdeploy
- fetched_at：2026-11-09T14:08:52Z
- sha256：`1c7dbbab2b0c9a41ce8687a991fbe2b60743f18d3d428d7f4a69cb3cb79fc423`
- 判定：hit — 正文含 12 个仓库内真实路径（阈值 3）
- 原文快照：`source.txt`（与判定元数据分文件存放）
