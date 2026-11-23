# gvergnaud/ts-pattern 深度分析

> 阅读档位：选型尽调（profile=adoption_due_diligence）
> 注意力预算：定位 15 / 架构 15 / 抽象 10 / ADR 10 / 扩展 5 / 经验卡 0 / 工程维护 45
> 证据约定：[事实] 确定性提取 · [判断] 有 file:line 或文档锚点 · [未获得] 当前未采集

## 导读

> **是什么**：🎨 The exhaustive Pattern Matching library for TypeScript, with smart type inference.
> **架构一句话**：[判断] 顶层以 `.`、`tests`、`src` 为主，入口为 `src/index.ts`（静态结构判断，未做动态跟踪）。
> **最大风险**：Top1 贡献者占比 91.03%，决策集中度需关注
> **不适合**：需要稳定 API/长期支持承诺的场景，请先核对发布节奏与维护状态；依赖链许可证与权重许可能力当前未采集，不能据此做出商用结论。

## 1. 项目定位与目标

[事实] gvergnaud/ts-pattern 属于 `未指定` 领域、`classic` 通道，主语言 TypeScript（97%），15,223 stars / 183 forks。

[事实] 项目自述：🎨 The exhaustive Pattern Matching library for TypeScript, with smart type inference.。

[事实] README 摘要：These files measure how expensive ts-pattern's types are for the TypeScript compiler, as opposed to the runtime benchmarks in the parent directory. They intentionally contain large `match` expressions of the shapes that show up in real codebases: - `large-union-exhaustive.ts`: a 200-member string literal union (the same shape as a large string enum), matched member by member. - `discriminated-union-exhaustive.ts`: a 20-variant discriminated union。

- **目标用户**：[判断] 模型工程师 / 推理基础设施开发者；应用与平台开发者
- **替代方案与差异**：[未获得] 本次未采集竞品对比与 roadmap，不得据此推断「没有替代品」。
- **不解决什么**：[未获得] 没有路线图与 issue 语料，无法可靠界定能力边界。

[判断] 阶段信号：仓库已存在 2,374 天，近一年发布 2 个版本，最近提交距今 3 天，维护状态「active」。这只说明是否仍在维护，不等于成熟度结论。

## 2. 架构全景

### 2.1 上下文边界

[判断] 架构说明文档：`README.md`, `benchmarks/compile-time/README.md`；边界结论来自文档与目录结构，未经运行验证。
[事实] 硬件/内核线索：vendors=[]、kernel_langs=[]。

### 2.2 模块职责

| 模块 | 文件数 | 职责（启发式） |
|---|---:|---|
| `.` | 9 | 业务实现（职责需人工确认） |
| `tests` | 57 | 测试与用例 |
| `src` | 20 | 核心实现 |
| `benchmarks` | 12 | 示例与基准 |
| `docs` | 3 | 文档 |

### 2.3 一次调用的路径（运行时视图）

[判断] 静态推断：`src/index.ts`, `src/types/index.ts` → 输出。内部 import 边约 0 条，只用于判断调用方向；**未做运行时跟踪**，参数与分支需读源码确认。

### 2.4 数据与控制流

[未获得] 未检测到并行/缓存轴证据；不代表项目中不存在。

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

## 3. 核心抽象与契约

[未获得] 本次源码切片未识别到显式接口/注册模式；这不等于项目没有抽象层，只说明当前采集粒度不足。

入口候选（可作为契约阅读起点）：`src/index.ts`、`src/types/index.ts`

## 4. 关键设计决策（ADR）

每条固定六字段：决策 / 替代 / 代价 / 证据 / 可复用规则 / 边界·反模式。

### ADR-1 · t1: v5 改为 .with 立即求值，不再惰性等待 .exhaustive

- **决策**：v5 改为 .with 立即求值，不再惰性等待 .exhaustive
- **替代**：v4 惰性累积分支，终结调用时才执行
- **代价**：未以 exhaustive/otherwise 收尾时行为静默改变
- **证据**：`docs/v4-to-v5-migration-guide.md:19`
- **可复用规则**：链式 API 提前求值可简化实现，但需在迁移文档中显式标注语义变更
- **边界/反模式**：仅当所有调用方都以终结方法收尾时安全；中途丢弃链式结果会误触发副作用

### ADR-2 · t2: 用 P.array/P.set/P.map 模式替代原生构造器匹配

- **决策**：用 P.array/P.set/P.map 模式替代原生构造器匹配
- **替代**：直接 .with(new Set(...)) / .with(new Map(...)) 匹配
- **代价**：破坏旧写法，用户需按迁移指南改写
- **证据**：`docs/v4-to-v5-migration-guide.md:47`
- **可复用规则**：模式匹配库应统一自有模式语法，避免依赖运行时构造器语义
- **边界/反模式**：对已有大量构造器匹配代码的存量项目，升级成本高，需评估迁移量

### ADR-3 · t3: v5 依赖 TS const 类型参数，硬性要求 TypeScript 5+

- **决策**：v5 依赖 TS const 类型参数，硬性要求 TypeScript 5+
- **替代**：兼容旧版 TS 以扩大用户面
- **代价**：放弃 TS4 及以下用户，升级门槛抬高
- **证据**：`docs/v4-to-v5-migration-guide.md:9`
- **可复用规则**：类型库可借新编译器特性换取推断精度，但须明确最低版本约束
- **边界/反模式**：用户被锁定在旧 TS 版本（如企业长期支持版）时不可采用

### ADR-4 · t4: 以 Instantiations 作为编译期性能主指标

- **决策**：以 Instantiations 作为编译期性能主指标
- **替代**：以 Check time 等墙钟时间衡量
- **代价**：需维护独立编译期基准文件与 trace 工具链
- **证据**：`benchmarks/compile-time/README.md:31`
- **可复用规则**：性能基准优先选确定性指标，避免墙钟噪声导致误判回归
- **边界/反模式**：Instantiations 不反映运行时开销；运行时热路径仍需单独基准

### ADR-5 · t5: 基准覆盖穷尽与非穷尽两种编辑中状态

- **决策**：基准覆盖穷尽与非穷尽两种编辑中状态
- **替代**：只测完整 match 表达式的编译开销
- **代价**：基准文件数量与维护成本翻倍
- **证据**：`benchmarks/compile-time/README.md:12`
- **可复用规则**：类型级库应把编辑器中间态纳入基准，因其是用户高频路径
- **边界/反模式**：对无类型推断负担的纯运行时库，此维度无意义

### ADR-6 · t6: 用 P 命名空间聚合模式构造器，替代顶层散装导出

- **决策**：用 P 命名空间聚合模式构造器，替代顶层散装导出
- **替代**：顶层导出 __、select、not、when 等
- **代价**：v3→v4 全面破坏性改名，用户需批量迁移
- **证据**：`docs/v3-to-v4-migration-guide.md:7`
- **可复用规则**：公共 API 收敛到单一命名空间可降低命名冲突与发现成本
- **边界/反模式**：早期用户基数大时改名代价高；需配套迁移指南与 codemod

## 5. 扩展与改造路径

[未获得] 未识别到显式插件/注册点。

[判断] 新增能力的静态路径（需按实际代码复核）：

1. 在入口处接入参数/配置（入口候选：`src/index.ts`, `src/types/index.ts`, `src`）；
2. 复用上表中的注册/分派结构，实现新的后端或适配器；
3. 补对应测试与文档，再走发布流程。

- 扩展文档：[未获得]
- 改造成本：[未获得] 需要先确认契约稳定性与测试覆盖，本报告不估算人日。

## 6. 经验卡

### 经验 1 · 链式 API 提前求值可简化实现，但需在迁移文档中显式标注语义变更

- **证据**：`docs/v4-to-v5-migration-guide.md:19`（来自 gvergnaud/ts-pattern）
- **适用边界**：仅当所有调用方都以终结方法收尾时安全；中途丢弃链式结果会误触发副作用
- **反模式**：在边界之外照搬「v5 改为 .with 立即求值，不再惰性等待 .exhaustive」，代价会变成「未以 exhaustive/otherwise 收尾时行为静默改变」
- **如果我来做**：先确认边界成立，再选择「v5 改为 .with 立即求值，不再惰性等待 .exhaustive」而非「v4 惰性累积分支，终结调用时才执行」

### 经验 2 · 模式匹配库应统一自有模式语法，避免依赖运行时构造器语义

- **证据**：`docs/v4-to-v5-migration-guide.md:47`（来自 gvergnaud/ts-pattern）
- **适用边界**：对已有大量构造器匹配代码的存量项目，升级成本高，需评估迁移量
- **反模式**：在边界之外照搬「用 P.array/P.set/P.map 模式替代原生构造器匹配」，代价会变成「破坏旧写法，用户需按迁移指南改写」
- **如果我来做**：先确认边界成立，再选择「用 P.array/P.set/P.map 模式替代原生构造器匹配」而非「直接 .with(new Set(...)) / .with(new Map(...)) 匹配」

### 经验 3 · 类型库可借新编译器特性换取推断精度，但须明确最低版本约束

- **证据**：`docs/v4-to-v5-migration-guide.md:9`（来自 gvergnaud/ts-pattern）
- **适用边界**：用户被锁定在旧 TS 版本（如企业长期支持版）时不可采用
- **反模式**：在边界之外照搬「v5 依赖 TS const 类型参数，硬性要求 TypeScript 5+」，代价会变成「放弃 TS4 及以下用户，升级门槛抬高」
- **如果我来做**：先确认边界成立，再选择「v5 依赖 TS const 类型参数，硬性要求 TypeScript 5+」而非「兼容旧版 TS 以扩大用户面」

### 经验 4 · 性能基准优先选确定性指标，避免墙钟噪声导致误判回归

- **证据**：`benchmarks/compile-time/README.md:31`（来自 gvergnaud/ts-pattern）
- **适用边界**：Instantiations 不反映运行时开销；运行时热路径仍需单独基准
- **反模式**：在边界之外照搬「以 Instantiations 作为编译期性能主指标」，代价会变成「需维护独立编译期基准文件与 trace 工具链」
- **如果我来做**：先确认边界成立，再选择「以 Instantiations 作为编译期性能主指标」而非「以 Check time 等墙钟时间衡量」

### 经验 5 · 类型级库应把编辑器中间态纳入基准，因其是用户高频路径

- **证据**：`benchmarks/compile-time/README.md:12`（来自 gvergnaud/ts-pattern）
- **适用边界**：对无类型推断负担的纯运行时库，此维度无意义
- **反模式**：在边界之外照搬「基准覆盖穷尽与非穷尽两种编辑中状态」，代价会变成「基准文件数量与维护成本翻倍」
- **如果我来做**：先确认边界成立，再选择「基准覆盖穷尽与非穷尽两种编辑中状态」而非「只测完整 match 表达式的编译开销」

## 附录 A 证据索引与未知项

### A1. 代码证据索引

| id | 决策 | 证据 |
|---|---|---|
| t1 | v5 改为 .with 立即求值，不再惰性等待 .exhaustive | `docs/v4-to-v5-migration-guide.md:19` |
| t2 | 用 P.array/P.set/P.map 模式替代原生构造器匹配 | `docs/v4-to-v5-migration-guide.md:47` |
| t3 | v5 依赖 TS const 类型参数，硬性要求 TypeScript 5+ | `docs/v4-to-v5-migration-guide.md:9` |
| t4 | 以 Instantiations 作为编译期性能主指标 | `benchmarks/compile-time/README.md:31` |
| t5 | 基准覆盖穷尽与非穷尽两种编辑中状态 | `benchmarks/compile-time/README.md:12` |
| t6 | 用 P 命名空间聚合模式构造器，替代顶层散装导出 | `docs/v3-to-v4-migration-guide.md:7` |

- 置信度：med
- 架构范式标签：模块化、深优化

### A2. 外部资料

- 来源：deepwiki
- url：https://deepwiki.com/gvergnaud/ts-pattern
- fetched_at：2026-11-23T22:32:02Z
- sha256：`3b5b0a32ca887b4d2da4619351c891b5a9b97f12f16a7d837cdafe8f20104d21`
- 判定：hit — 正文含 4 个仓库内真实路径（阈值 3）
- 原文快照：`source.txt`（与判定元数据分文件存放）

### A3. 未获得项

- 依赖链许可证、模型权重/数据许可、CLA —— 未采集；
- issue/PR 响应质量、CI 运行结果 —— 未采集；
- roadmap、竞品对比、用户画像 —— 未采集；
**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算


## 附录 B 许可证 / 维护 / 工程 / 成本

### B1. 许可证与合规风险

[事实] 主许可证 **MIT**；组织类型 personal；治理文档：未检出。

[未获得] 依赖链是否存在 GPL/AGPL、模型权重与数据集许可、CLA 要求；这些必须人工或由后续数据源补齐，本报告不给出「可商用」结论。

### B2. 维护状态与风险

[事实] 贡献者 30 人，Top1 占比 91.03%；近 90 天 / 365 天提交 32 / 58 次；最近提交距今 3 天，维护状态「active」。

- Top1 贡献者占比 91.03%，决策集中度需关注
- 未检出治理文档，贡献与决策流程可能不透明

### B3. 运行与工程体系

[事实] 仓库约 118 个文件、1.2 MiB；本次采集 9 个源码切片（tarball `2f65e07b603da608`）。
[事实] 语言构成：JavaScript 2.55%、Shell 0.13%、TypeScript 97.32%；硬件 vendors=[]、kernel_langs=[]。

[未获得] 构建脚本、依赖安装、测试体系、CI/CD、配置与 secret 管理未采集；本报告不能回答「能否在目标环境跑起来」。

**特征卡已知限制**：

- 证据来自 9 个源码切片的逐行扫描，未覆盖文件不计入
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B4. 运行元数据与成本

| 项 | 值 |
|---|---|
| 仓库 | gvergnaud/ts-pattern |
| commit | `05e20b6698228090ed3d86039db75a81eca2a673` |
| 分析基准时间 (as-of) | 2026-11-23T12:52:56Z |
| 通道 / 领域 | classic / 未指定 |
| 请求档位 (requested_depth) | fast |
| **实际档位** (actual_depth) | fast |
| 降级原因 (reason) | baseline — 按通道基线 |
| 配额状态 (quota_state) | strong 0/1、fast 0/5（周起点 2026-11-23）；tokens 周 0/2000000、月 344238/6000000（月起点 2026-11-01） |
| 快照 sha256 | `a51094bc0f76b9fec9a9c064ea158287e449ee56a053afc8d76ccd8565858e46` |
| 成本说明 | 本次 ¥0.0229（模型调用 1 次）；输入 9,018 tok / 命中 256 tok / 输出 676 tok |
| 累计 | 本周 ¥0.0229 / 9,694 tok；本月 ¥1.0532 / 353,932 tok |
| 单价 | deepseek-flash 输入未命中 ¥2/M · 缓存命中 ¥0.04/M · 输出 ¥8/M（官方中文页，核对 2026-11-03，取高峰价；低谷约为一半） |
| 口径 | 本次分析的成本（不含开发期重复调用）；账户累计见 cost；成本说明同 as-of 重跑不变（幂等优先）；两者不一致是设计，不是 bug |

**档位决策链路**：

1. L1 通道基线：classic → strong；自动链按 auto_default=fast 取更省档位 → fast（非 L4 人工 override）
2. 凭据：齐全
3. L2 周配额：fast 已用 0/5，未用满
4. L3 预算：估算 5598 × 安全系数 1.3 = 7277 tok（单选上限 120000），周 0/2000000
5. 结论：实际档位 fast（按通道基线）

**上下文组装**（裁剪发生在调用之前）：

| 块 | 优先级 | 估算 token |
|---|---|---|
| featcard | 1 | 1,054 |
| readme | 2 | 341 |
| source_files:.github/FUNDING.yml | 4 | 216 |
| source_files:.github/ISSUE_TEMPLATE/bug_report.md | 4 | 146 |
| source_files:.github/ISSUE_TEMPLATE/feature_request.md | 4 | 164 |
| source_files:docs/roadmap.md | 4 | 655 |
| source_files:docs/v3-to-v4-migration-guide.md | 4 | 1,511 |
| source_files:docs/v4-to-v5-migration-guide.md | 4 | 1,511 |

- 丢弃：—
- 合计 5,598 / 上限 120,000

### B5. 特征卡摘要

- 卡文件：`data/featcards/gvergnaud__ts-pattern__05e20b6698228090ed3d86039db75a81eca2a673.json`（schema 1.0）
- 入口文件：src/index.ts, src/types/index.ts
- 最大目录深度：4；monorepo：是
- 源码切片：9 个文件（tarball `2f65e07b603da608`）
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
- 治理文档：否

**依赖图**（内部模块 import 边，节点/边排序后输出）

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

**已知限制**：

- 证据来自 9 个源码切片的逐行扫描，未覆盖文件不计入
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B6. 体检事实（确定性，零 LLM）

| 指标 | 值 |
|---|---|
| Star / Fork | 15,223 / 183 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 30 / 91.03% |
| Top10 贡献集中度 | 97.80% |
| 90 天 / 365 天提交 | 32 / 58 |
| 最近提交 / 距今天数 | 2026-11-20T23:18:43Z / 3 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 2,374 天 / 2 |
| 组织类型 / 许可证 | personal / MIT |
| 文件数 / 体积 | 118 / 1.2 MiB |
| 内部模块依赖边 | 0 |

**语言构成**：JavaScript 2.55%、Shell 0.13%、TypeScript 97.32%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| . | 9 | 665,408 |
| tests | 57 | 408,164 |
| src | 20 | 131,747 |
| benchmarks | 12 | 51,738 |
| docs | 3 | 19,542 |
| scripts | 3 | 14,332 |
| examples | 11 | 11,831 |
| .github | 3 | 1,974 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算
