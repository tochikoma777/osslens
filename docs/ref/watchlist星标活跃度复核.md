# 开源项目 Watchlist 复核报告：截至 2026-10-30 的 Star、活跃度与状态

## 摘要：仓库活跃度高度分化，原始 Watchlist 存在组织归属和项目口径错误

截至 2026-10-30，本次复核的 19 个仓库中，18 个仓库可通过 GitHub REST API 直接核验，TGI 仓库则因已归档而无法由 API 返回仓库统计字段。复核结果同时纠正了两处原始条目错误：`DeepInfer` 确已开源，但地址是 `deepseek-ai/DeepInfer`，不是独立组织；`volcengine/veRL` 不存在，veRL 的真实地址是 `verl-project/verl`，其由字节跳动 Seed 团队发起、后迁移至 verl 社区维护。

DeepSeek 系项目并非整体活跃。FlashMLA、DeepEP、DeepGEMM、DeepInfer 和 deepseek-recipe 的首次提交均在 2026-10-19 至 2026-10-27 之间；3FS、DeepSeek-OCR、DualPipe、smallpond 和 EPLB 则分别停留在 2026-05-07、2026-01-27、2026-01-14、2025-03-05 和 2025-03-24。因此，原始 watchlist 至少应按“近期迭代组件”“历史一次性开源组件”和“归档或冻结项目”分层，而不能继续按单一 DeepSeek 生态整体跟踪。

两个反例事实均已获官方文本证实：TGI 已进入维护模式，官方 README 明确推荐继续使用 vLLM、SGLang，以及兼容本地场景的 llama.cpp 或 MLX；AutoGen 仓库也明确进入 maintenance mode，新用户应转向 Microsoft Agent Framework。两项事实都不能表述为仓库已经完全关闭，因为 TGI 仍接受轻微修复、文档改进和轻量维护 PR，AutoGen 仓库也未归档。

DeepInfer 是 Apache License 2.0 项目，当前开源版本支持 NVIDIA SM100 和华为 Ascend 950，但只提供离线推理示例。KV cache 系统、VE/Prefill/Decode 分离，以及 Prefill 与 Decode 数据并行副本之间的负载均衡均未包含在当前版本中。DeepInfer 不能按“完整在线推理服务”口径与 vLLM、SGLang 直接比较。[8][9][10]

## 1. 复核结果按提交冷度形成三个层级，单一“活跃度排序”已经失真

本次复核执行于 2026-10-30（Asia/Shanghai）。GitHub REST API 查询时间与字段口径如下：`stargazers_count` 为公开仓库主页展示的 Star 数；`forks_count` 为 Fork 数；“最近提交时间”为默认分支最新提交的 committer date；`archived` 为 GitHub 归档标志。第三方聚合页面仅用于交叉检查，不替代 API 主字段。[1]

报告没有沿用 2026-10 版 watchlist 中的旧数值，全部统计字段均在本次执行时重新取得。API 返回时，18 个仓库的字段结构一致，可以横向比较；TGI 属于唯一例外，其归档状态阻断了统计字段返回，因此单独采用官方仓库页面及 README 文本。

**“维护状态”是本次复核的判断结果，不等于 GitHub 官方标签。** 判断规则是：30 天内存在提交记为“活跃”，30 至 180 天记为“放缓”，超过 180 天或长期无实质性迭代记为“停止维护”，仓库主动宣布后续仅接收维护类贡献记为“维护模式”，GitHub 归档标志为真且维护公告并存记为“归档/维护模式”。

这一区分直接影响排序结论。仓库当前仍显示提交，不代表项目正在主动扩展；README 或官方文档宣布进入维护模式，也不代表仓库已停止接受任何 PR。若把“近期有提交”和“项目正在扩展”视为同一概念，就会高估 TGI 的当前开发强度，同时低估 AutoGen 代码库继续接收修复的可能。

![18 个仓库的最近提交冷度](/data/workspace/dr:20261030_watchlist_review/fig_activity.png)

*图 1：TGI、smallpond 与 EPLB 距最近一次提交超过 220 天，绿色项目为 14 天内提交。数据来源：GitHub REST API，核对时间 2026-10-30 [1]*

**可下载数据表已保存为 [结构化复核数据](/data/workspace/dr:20261030_watchlist_review/data_watchlist.csv)。**

| 组别 | 项目 | 真实地址 | Star | Fork | 最近提交（北京时间） | 维护状态 | 核对日期 | 数据来源 |
|---|---|---|---:|---:|---|---|---|---|
| A | FlashMLA | `deepseek-ai/FlashMLA` | 13,223 | 1,251 | 2026-10-27 | 活跃 | 2026-10-30 | GitHub API [1] |
| A | DeepEP | `deepseek-ai/DeepEP` | 10,389 | 1,530 | 2026-10-21 | 活跃 | 2026-10-30 | GitHub API [1] |
| A | DeepGEMM | `deepseek-ai/DeepGEMM` | 9,130 | 1,493 | 2026-10-20 | 活跃 | 2026-10-30 | GitHub API [1] |
| A | DualPipe | `deepseek-ai/DualPipe` | 3,031 | 339 | 2026-01-14 | 停止维护 | 2026-10-30 | GitHub API [1] |
| A | EPLB | `deepseek-ai/EPLB` | 1,466 | 213 | 2025-03-24 | 停止维护 | 2026-10-30 | GitHub API [1] |
| A | 3FS | `deepseek-ai/3FS` | 10,400 | 1,140 | 2026-05-07 | 放缓 | 2026-10-30 | GitHub API [1] |
| A | smallpond | `deepseek-ai/smallpond` | 5,028 | 458 | 2025-03-05 | 停止维护 | 2026-10-30 | GitHub API [1] |
| A | tilelang | `tile-ai/tilelang` | 8,857 | 941 | 2026-10-30 | 活跃 | 2026-10-30 | GitHub API [1] |
| A | DeepSeek-OCR | `deepseek-ai/DeepSeek-OCR` | 24,101 | 2,211 | 2026-01-27 | 放缓 | 2026-10-30 | GitHub API [1] |
| A | DeepInfer | `deepseek-ai/DeepInfer` | 24,445 | 2,944 | 2026-10-25 | 活跃 | 2026-10-30 | GitHub API、官方 README [1][8] |
| A | deepseek-recipe | `deepseek-ai/deepseek-recipe` | 2,650 | 405 | 2026-10-19 | 活跃 | 2026-10-30 | GitHub API [1] |
| A | DeepSpec | `deepseek-ai/DeepSpec` | 7,267 | 694 | 2026-07-09 | 放缓 | 2026-10-30 | GitHub API [1] |
| B | vLLM | `vllm-project/vllm` | 95,914 | 24,186 | 2026-10-30 | 活跃 | 2026-10-30 | GitHub API [1] |
| B | SGLang | `sgl-project/sglang` | 38,305 | 10,028 | 2026-10-30 | 活跃 | 2026-10-30 | GitHub API [1] |
| B | TGI | `huggingface/text-generation-inference` | API 未返回 | API 未返回 | 2026-03-21 | 归档/维护模式 | 2026-10-30 | GitHub API、官方 README [1][9] |
| B | AutoGen | `microsoft/autogen` | 61,632 | 9,333 | 2026-10-28 | 维护模式 | 2026-10-30 | GitHub API、官方 README [1][10] |
| B | veRL | `verl-project/verl` | 24,075 | 4,840 | 2026-10-30 | 活跃 | 2026-10-30 | GitHub API [1] |
| B | Megatron-LM | `NVIDIA/Megatron-LM` | 18,298 | 4,688 | 2026-10-30 | 活跃 | 2026-10-30 | GitHub API [1] |

表中“API 未返回”只表示归档仓库的统计字段没有在本次接口调用中取得，不等于 Star/Fork 不存在。仓库归档后，网页通常仍可展示历史统计，但本次没有使用其网页概览数回填，以避免引入与 API 口径不一致的数据。

## 2. A 组呈现两种完全不同的项目节奏，不能按 DeepSeek 品牌合并排序

A 组实际由近期迭代项目和历史组件两层构成。DeepInfer、FlashMLA、DeepEP、DeepGEMM 与 deepseek-recipe 属于近期连续修改的组件层；3FS、DeepSeek-OCR、DualPipe、smallpond 和 EPLB 则已明显进入低频或停止状态。若继续采用统一的“DeepSeek 生态活跃度”，统计结果会把品牌关注度与项目开发活跃度混为一谈。

**近期组件层可以优先复核，历史组件层应按冻结参考实现处理。** DeepInfer 最新提交发生在 2026-10-25，FlashMLA 为 2026-10-27，DeepEP 为 2026-10-21，DeepGEMM 为 2026-10-20，deepseek-recipe 为 2026-10-19；tilelang 的默认分支最新提交则为 2026-10-30。这些仓库均未满 14 天，适合列为“近期变更优先复核”对象。[1]

与之相比，3FS 最后一次提交为 2026-05-07，距今约 176 天；DeepSeek-OCR 为 2026-01-27，距今约 276 天；DualPipe 为 2026-01-14，距今约 289 天；smallpond 为 2025-03-05，距今约 575 天；EPLB 为 2025-03-24，距今约 556 天。上述仓库虽然仍是公开项目，且未被 GitHub 归档，但提交间隔已经显著超过“活跃”阈值。[1]

这一分层意味着，近期组件层适合跟踪缺陷修复、接口变化和版本兼容；历史组件层更适合作为固定架构或算法参考，不适合因 Star 数较高而假定其仍在持续扩展。尤其是 smallpond 和 EPLB，最近提交已超过一年半，应将“仓库仍可访问”和“项目仍在开发”明确区分。

**Star 与提交频率没有形成统一关系，关注度不能替代活跃度。** DeepSeek-OCR 拥有 24,101 个 Star，但最近一次提交为 2026-01-27；EPLB 只有 1,466 个 Star，最近提交也停留在 2025-03-24。两者的开发节奏相近，而可见关注度相差约 16.4 倍。相反，FlashMLA 拥有 13,223 个 Star，DeepEP 拥有 10,389 个 Star，最近提交分别仅距核对日 3 天和 9 天。[1]

| 状态分组 | 仓库 | Star | 距最近提交天数 | 复核含义 |
|---|---|---:|---:|---|
| 近期迭代 | DeepInfer、FlashMLA、DeepEP、DeepGEMM、deepseek-recipe、tilelang | 2,650–24,445 | 0–11 | 适合优先跟踪变更 |
| 已放缓 | DeepSpec、3FS、DeepSeek-OCR、DualPipe | 3,031–24,101 | 113–289 | 可作为稳定或历史参考 |
| 停止维护 | smallpond、EPLB | 1,466–5,028 | 556–575 | 不应按近期开发项目排序 |

“停止维护”在本报告中只表示最近提交已超过 180 天，且未观察到本轮复核期间的实质性迭代，不表示代码不可用、许可证失效或官方发布删除。若后续出现新分支、安全修复或组织迁移，应重新核对仓库状态，而不能继续沿用本报告中的长期判断。

## 3. DeepInfer 已经真实开源，但当前交付边界是离线推理核心，不是完整在线服务

DeepInfer 并非传言或伪仓库。官方仓库 `deepseek-ai/DeepInfer` 采用 Apache License 2.0，截至 2026-10-30 拥有 24,445 个 Star、2,944 个 Fork，默认分支最近提交时间为 2026-10-25。其 README 明确称 DeepInfer 为“支撑 DeepSeek 大规模生产服务的高性能推理框架”，并说明本次开源版本提供“offline inference with the core features needed for serving at scale”。[8]

**当前支持范围只有 NVIDIA SM100 和 Ascend 950，不能扩展解释为所有 NVIDIA GPU 或所有昇腾 NPU。** 官方 README 明确列出两类目标硬件：NVIDIA SM100 GPU 和 Huawei Ascend 950 NPU。软件依赖分别为 Linux、GCC 13.0 及以上、Python 3.12、CUDA 13 或 CANN 9.2。[8]

因此，当前文档支持的结论是“支持 NVIDIA SM100 和 Ascend 950”，而不是“覆盖所有 NVIDIA GPU 架构”或“覆盖所有华为昇腾 NPU”。若脱离具体 SM 与 CANN 版本讨论硬件兼容性，会把目标硬件集合错误扩大。

**“离线推理”不是第三方推测，而是官方当前交付形态。** README 在“Offline inference”章节给出的入门命令是运行 `examples/offline_inference.py`，默认检查点 `deepseek-ai/DeepSeek-V4.1-Flash-1017` 在首次运行时下载。[8]

当前 README 没有给出可与 vLLM 或 SGLang 对等的在线服务入口、Prefill/Decode 分离部署协议，或数据并行副本负载均衡组件。因此，现有证据支持“当前版本主要提供离线推理”的判断，但不支持“永远只能离线推理”。本次发布没有包含相关服务模块，不代表后续版本不会补充。

**当前开源范围明确排除了三项在线服务能力。** README 将以下三项列为“A complete inference service”仍然需要、但当前版本未包含的内容：

| 未包含能力 | 官方措辞与含义 | 可支持的复核结论 |
|---|---|---|
| KV cache 系统 | “A KV cache system” | 当前版本不包含 |
| VE/Prefill/Decode 分离 | “VE/Prefill/Decode disaggregation” | 当前版本不包含；README 称大部分所需引擎功能已实现 |
| Prefill/Decode 副本负载均衡 | “Load balancing across data-parallel replicas for both prefill and decode” | 当前版本不包含 |

README 对 Prefill/Decode 分离的括号补充说明是“most required engine functionality is already implemented”。这表明部分底层能力可能已经具备，但不能据此推导完整的 PD 分离控制面、KV 传输、在线请求调度或副本负载均衡已经开源。现有文本明确列示的是“未包含”，而不是“已经包含”。

**模型与特性范围同样有限，DeepInfer 不是通用、多模型推理服务器。** 官方 README 仅列出 DeepSeek-V4.1-Flash 为当前支持模型，并包含优化 kernel、模型与采样器运行时、Attention DP / balanced CP、MoE EP + EPLB、DSpark、置信度调度验证、SWA bounded replay、异步调度、batch-invariant inference、确定性采样和结构化输出。[8]

上述特性足以说明 DeepInfer 提供了复杂的推理核心，却不足以证明其已覆盖通用在线服务所需的请求路由、服务发现、长时缓存管理和跨副本调度。与 vLLM、SGLang 比较时，必须同时比较“推理核心能力”和“生产服务组件”两个不同层次。

## 4. B 组的真正分界线是持续开发还是进入维护，而不是仓库是否仍可访问

B 组五个项目并非全部处于持续扩展状态。vLLM、SGLang、veRL 和 Megatron-LM 的最近提交均落在 2026-10-30；AutoGen 的最新提交为 2026-10-28，但其仓库已明确进入 maintenance mode；TGI 则兼具官方维护模式公告与 GitHub 归档标志。

**四项目在核对日仍有当日提交，但项目定位并不相同。** vLLM 拥有 95,914 个 Star 和 24,186 个 Fork；SGLang 拥有 38,305 个 Star 和 10,028 个 Fork；veRL 拥有 24,075 个 Star 和 4,840 个 Fork；Megatron-LM 拥有 18,298 个 Star 和 4,688 个 Fork。四个仓库默认分支的最近提交均为 2026-10-30。[1]

其中，veRL 的真实组织是 `verl-project`，不是 `volcengine`。项目由 ByteDance Seed 团队发起，随后迁移至 verl 社区维护；`volcengine/veRL` 在本次 API 查询中没有返回有效仓库字段，故记为“未核实”，不能将其 Star、Fork 或最近提交时间补入表格。[11]

![watchlist 仓库 Star 数对比](/data/workspace/dr:20261030_watchlist_review/fig_stars.png)

*图 2：vLLM 与 SGLang 的 Star 数显著高于其余对照项目。数据来源：GitHub REST API，核对时间 2026-10-30 [1]*

**Star 数反映的是项目可见度和历史累积，不能单独证明开发活跃度。** vLLM 与 SGLang 的 Star 数分别为 95,914 和 38,305，远高于 veRL 的 24,075 与 Megatron-LM 的 18,298。但后两者在核对日均存在提交，因此“Star 更高”只能说明社区关注度更高，不能推出“开发活动更强”。

| 项目 | Star | Fork | 最近提交 | 状态判断 |
|---|---:|---:|---|---|
| vLLM | 95,914 | 24,186 | 2026-10-30 | 活跃 |
| SGLang | 38,305 | 10,028 | 2026-10-30 | 活跃 |
| veRL | 24,075 | 4,840 | 2026-10-30 | 活跃 |
| Megatron-LM | 18,298 | 4,688 | 2026-10-30 | 活跃 |
| AutoGen | 61,632 | 9,333 | 2026-10-28 | 维护模式 |
| TGI | API 未返回 | API 未返回 | 2026-03-21 | 归档/维护模式 |

活跃度的有效判断需要同时结合提交频率、官方维护公告和归档状态。仅凭 Star 或 Fork 排序，会把 AutoGen 的高历史关注度误读为与新项目同等级别的开发投入；反过来，低 Star 项目也可能因近期提交而具有更高的版本变化风险。

## 5. TGI 已停止新功能开发并归档，官方明确推荐 vLLM 和 SGLang

TGI 的当前状态不是普通低频维护，而是官方维护模式与 GitHub 归档并存。其 README 和迁移文档均声明，自 2025-12-11 起，项目只接受有限类型的贡献，而新部署应使用其他引擎。

**Hugging Face 官方已经明确建议新部署转向 vLLM、SGLang 及其他引擎，但现有部署并未被宣布立即失效。** Hugging Face 官方 README 的原文是：“text-generation-inference is now in maintenance mode. Going forward, we will accept pull requests for minor bug fixes, documentation improvements and lightweight maintenance tasks.”

同一公告继续说明：“This approach is now adopted by downstream inference engines, which we contribute to and recommend using going forward: vllm, SGLang, as well as local engines with inter-compatibility such as llama.cpp or MLX.”[9]

**维护模式与归档共同决定 TGI 的当前定位，二者不能只取其一。** Hugging Face 官方迁移文档给出的生效日期为 2025-12-11，并明确仅接收 minor bug fixes、文档改进和轻量维护类 PR。GitHub API 返回 `archived=true`，最近一次提交为 2026-03-21。[1][2]

因此，“TGI 是否已停止维护”的准确答案是：已停止新功能开发并进入维护模式，且仓库已归档。它仍可接收有限维护 PR，但本次证据不能支持“官方宣布 TGI 将在某日彻底删除”或“所有现有 TGI 部署立即失效”的结论。

**官方推荐存在明确的场景边界，不能压缩成单一技术选型。** 官方文本明确列出的选项包括：

| 使用场景 | 官方提及的推荐或兼容引擎 |
|---|---|
| 一般推理服务 | vLLM、SGLang |
| 本地推理 | llama.cpp、MLX |
| 官方端点迁移 | vLLM、SGLang |

因此，可以确认“Hugging Face 官方推荐转向 vLLM/SGLang”；但不能把官方文本概括成“Hugging Face 建议所有场景一律只使用 vLLM 或 SGLang”。本地和兼容场景仍有 llama.cpp、MLX 等选项。[2][9]

## 6. AutoGen 进入 Maintenance Mode，但仓库仍可接收社区维护贡献

AutoGen 的事实状态比“项目停止更新”更具体：README 明确宣布进入 maintenance mode，新用户应转向 Microsoft Agent Framework，但仓库未归档，仍可能出现提交。

**AutoGen 已明确进入 Maintenance Mode，官方引导新用户转向 Microsoft Agent Framework。** GitHub API 显示，`microsoft/autogen` 未归档，拥有 61,632 个 Star、9,333 个 Fork，最近提交时间为 2026-10-28。[1]

AutoGen 官方 README 在标题中使用“AutoGen is now in maintenance mode. It will not receive new features or enhancements and is community managed going forward. New users should start with Microsoft Agent Framework.”官方迁移文档则指出，Microsoft 已将 AutoGen 与 Semantic Kernel 合并到 Microsoft Agent Framework。[10][3]

因此，“AutoGen 是否进入 maintenance mode”可明确证实为“是”。但“maintenance mode”只表示不接收新功能或增强，不表示仓库已经归档、无法使用或永远不会再出现提交。2026-10-28 的提交也证明，仓库层面的代码活动并未完全停止。

**“微软是否转向 Microsoft Agent Framework”应表述为官方战略转向，而不是 AutoGen 仓库立即停止存在。** Microsoft Learn 将 Agent Framework 定义为 AutoGen 与 Semantic Kernel 的前进路径，并说明其由 AutoGen 与 Semantic Kernel 的核心团队开发。[3]

官方 README 面向新用户给出明确转向建议，迁移文档也以合并后的 Agent Framework 作为承接项目。现有证据足以确认战略重心转移，但不能进一步推出“AutoGen 代码库已经删除”“社区分支 AG2 由微软控制”，或“AutoGen 不再接收任何提交”。

| 待核实事实 | 核实结论 | 官方证据边界 |
|---|---|---|
| TGI 是否停止维护 | 已停止新功能开发，进入 maintenance mode | 官方 README 仅接受轻微修复、文档和轻量维护 PR [9] |
| TGI 是否建议转向 vLLM/SGLang | 是，官方明确推荐 | 同时提及 llama.cpp、MLX 等本地兼容引擎 [9] |
| TGI 仓库状态 | 已归档 | API 返回 `archived=true`，最近提交为 2026-03-21 [1] |
| AutoGen 是否进入 maintenance mode | 是 | 官方 README 明确使用“maintenance mode” [10] |
| 微软是否转向 Microsoft Agent Framework | 是，官方建议新用户使用 | AutoGen 与 Semantic Kernel 合并至 Agent Framework [3] |
| AutoGen 是否已归档 | 否 | API 返回 `archived=false` [1] |

## 7. 原始条目共存在两处确凿错误，另有三项能力不能补写或推断

原始 watchlist 中的错误可以明确纠正：DeepInfer 的真实组织是 `deepseek-ai`，veRL 的真实组织是 `verl-project`。对于当前版本没有公开说明的内容，报告保持“未核实”，不使用社区解读、媒体转述或旧版本资料补足。

**DeepInfer 的真实地址是 `deepseek-ai/DeepInfer`，不是独立组织 `DeepInfer`。** 官方仓库显示其全称为“High-performance, large-scale inference framework for DeepSeek models”，Star、Fork、最近提交和维护状态均已通过 API 核实。[1][8]

这一纠正同时影响项目归属判断。DeepInfer 应归入 DeepSeek 官方开源项目，而不是被处理为独立的第三方组织；其近期提交频率也应据此纳入 DeepSeek 系近期组件层，而不是与历史组件混排。

**`volcengine/veRL` 不是可核验的真实地址，veRL 的真实组织是 `verl-project`。** veRL 项目由 ByteDance Seed 团队发起，随后迁移至 verl 社区维护。原始条目将所有者写作 `volcengine`，且把项目名写为小写 `veRL`，均与当前官方组织路径不符。[11]

本次 API 对 `verl-project/verl` 取得了有效字段，因此真实项目可以纳入复核；`volcengine/veRL` 则因未返回有效仓库字段记为“未核实”。后续 watchlist 应直接保存规范化组织路径，避免再次出现名称大小写和组织归属不一致的问题。

**没有证据支持的字段不作推断。** 本报告没有声称“TGI 最后一次发布的具体版本”，没有把 TGI 网页展示的 Star/Fork 回填至 API 未返回的字段，也没有声称 DeepInfer 包含或排除了其 README 没有列出的其他在线服务组件。

本次也没有对未列入的仓库进行横向扩展检索。因此，当前结论只覆盖原始 watchlist 与本次核实清单，不代表对全部 DeepSeek、Hugging Face、Microsoft 或火山引擎项目的完整状态普查。

## 引用来源

[1] https://api.github.com/repos/deepseek-ai/DeepInfer
> “stargazers_count”: 24445, “forks_count”: 2944, “archived”: false, “pushed_at”: “2026-10-25T11:59:27Z”

[2] https://huggingface.co/docs/inference-endpoints/en/user-guides/migration/tgi
> “Text Generation Inference is in maintenance mode as of 12/11/2025.”

[3] https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/
> “AutoGen and Semantic Kernel are merging into a new, unified framework: Microsoft Agent Framework.”

[4] http://agentsindex.ai/autogen
> “Microsoft put AutoGen into maintenance mode in April 2026, directing new projects to Microsoft Agent Framework.”

[5] https://www.gitgenius.co/organizations/deepseek?sort=name
> “DeepSeek-OCR by deepseek-ai Total Stargazers:24,095”

[6] https://www.promptquorum.com/zh/power-local-llm/autogen-review
> “Microsoft 自身的 microsoft/autogen 仓库自 2025 年 10 月起进入维护模式。”

[7] https://kongchang.com/en/articles/langgraph-vs-crewai-vs-autogen-2026-ai-agent-framework-selection-guide
> “AutoGen is now in maintenance mode. It will not receive new features or enhancements and is now community-managed.”

[8] https://github.com/deepseek-ai/DeepInfer
> “This open-source release provides offline inference with the core features needed for serving at scale.”

[9] https://github.com/huggingface/text-generation-inference
> “text-generation-inference is now in maintenance mode. Going forward, we will accept pull requests for minor bug fixes, documentation improvements and lightweight maintenance tasks.”

[10] https://github.com/microsoft/autogen
> “AutoGen is now in maintenance mode. It will not receive new features or enhancements and is community managed going forward.”

[11] http://www.pickgithub.com/projects/2430
> “verl is a RL training library initiated by ByteDance Seed team and maintained by the verl community.”
