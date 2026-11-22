# Changelog

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本号遵守语义化版本。

## [Unreleased] - 2026-11-22 · 审查整改 + 合规重构（转 public 前置）

- **CI 修复**：`scripts/auto_persist.sh` 在 rebase 前设仓库级 `git config user.*`，修复并行 job 致远端推进时 `git rebase` 缺 committer identity 的失败（真实 run 44798310784 / 44598357662）；dispatch run `45029228666` 命中 rebase 并成功，验证闭合。
- **文档状态值同步**：README 227→231 tests；CODEBUDDY/锚文件当前声明 23→24 产物、台账 36→38 行（历史记录行保留）；`auto.yml` cron 注释消除矛盾。
- **合规重构（重大，不可逆）**：转 public 前用 `git filter-repo` 从全部历史剔除 `data/snapshots/**/src/`（243 文件 / 3.9 MB 第三方源码切片），规避许可证/署名再分发义务；`external/` 不可再生真源全部保留。146 commit 保留、git 33M→15M、tag l0–l5 重打并强推对齐。功能无影响：门禁绿、`site --check --strict` 一致（25 产物）、报告/站点 blob 不变；`test_l1.py:351` 因无真实切片按约定 skip（`230 passed, 1 skipped`）。
- **MIT LICENSE**：新增 LICENSE（commit `05658c8`）。
- **待办**：仓库仍 PRIVATE——fine-grained PAT 改可见性返回 HTTP 403，需负责人网页或 classic token 完成转 public。

## [Unreleased] - 2026-11-19 · 发现主题轮转 + agent 基础设施

- **主题 3 → 4**：新增 `topic:ai-agent`，只收基础设施型（sandbox / protocol / orchestration / runtime / tool-use / multi-agent framework），排除个人助理、聊天壳、教程与 prompt 集合。
- **每主题独立关键词**：`queries` 支持 `{q, require, exclude}`（字符串写法仍兼容）；此前全局 `exclude: agent` 会把 agent 主题全部剔光。
- **按日轮转**：每日取 1 个，起点由 `as_of` 日序决定（可复算、无状态），空主题自动跳过；避免全局 stars 排序被 30 万星项目垄断。
- **决策依据与被否决方案**：见 `docs/设计方案.md` §6.6（v1.8）。
- 测试 225 → **227**（轮转、每主题过滤覆盖、配置对象解析）。

## [Unreleased] - 2026-11-19 · pool.skip 跳过已消失仓库

- **配置**：`pool.skip`（owner/repo 列表，大小写不敏感、非法项 fail-fast）；`pool discover` 不会重新加入，`pool eligible` 不再列为候选，`pool add` 显式拒绝，每日观测经 `observe_targets()` 过滤。
- **用途**：`microsoft/onnxruntime` 已 404，加入 `skip` 后每日建池不再反复请求失败。
- **测试**：新增 4 条（解析/非法项、discover 排除、observe_targets、pool add 拒绝）；全仓 221 → **225**。

## [Unreleased] - 2026-11-19 · 空证据守卫与 onnxruntime 归因

- **修复（成本）**：`chat_json` 在“items 为空 / 输出顶格”判废分支丢弃了 usage，导致已计费调用不入账；现保留 usage 并记入台账。
- **修复（无效调用）**：`_run_insight` 在**无源码切片**（allowed_paths 为空）时不再发起模型调用——没有 `file:line` 可引用，模型必然返回空 items；报告改为如实写“无源码切片…未发起模型调用”。闸门顺序保持“调用上限 → 证据条件 → 发请求”。
- **onnxruntime 归因**：`microsoft/onnxruntime` 仓库本身返回 404（元数据/commits 均 404，疑似改名或下线），因此 codeload 也 404；不是模型问题。报告保留并标注证据缺失。
- 测试 219 → **221**（usage 保留 + 空证据守卫）。

## [Unreleased] - 2026-11-19 · 自动发现建池 + v3 全量重建

- **每日自动发现（原需求补齐）**：新增 `pool discover [--apply]`，调用 GitHub Search `/search/repositories`（`topic:llm|inference|cuda` + `stars:>=5000`，零 LLM）；本地再剔除 archived / fork / 低星 / 久未更新 / 已入池，按 stars 降序去重后取 `max_new_per_run` 个（**默认 1**，与每周 fast=5 的分析能力匹配，避免池子膨胀快于分析）；`pool.yml` 在「追加观测」前执行 `--apply`。
- **配置**：`pool.discovery`（`enabled` / `queries` / `per_page` / `max_new_per_run` / `min_stars` / `max_pushed_age_days`），非法值 fail-fast；默认值与模板同步。
- **报告全量转 v3**：11 份 v1/v2a 报告归档到 `reports/archive/2026-11/`（不参与站点与“已分析”判断），9 个仓库按 v3 重跑：8 份产出 5 张经验卡，`microsoft/onnxruntime` 因 codeload 404 + LLM 空输出未产出 ADR（如实标注，待跟进）。
- **站点**：旧报告页清理，产物 **24 → 21**（12 固定页 + 9 报告页）；`site --check --strict` 一致。
- **测试 212 → 218**：新增 `tests/test_discovery.py` 6 条（过滤/去重/上限/配置校验/dry-run 不写盘/单仓失败不阻断/CI 接线）。
- **成本**：批量 8 次 fast 实跑增量约 **¥0.24**；台账 20 → 27 行。

## [Unreleased] - 2026-11-19 · 解析修复与每日分析

- **修复**：`parse_insight()`（实时 HTTP 响应路径）漏解析 `rule` / `boundary`，导致模型即使输出也被静默丢弃；`Insight.from_json`（缓存路径）此前已解析，两条路径行为不一致。现两条路径统一，并新增回归测试。
- **缓存 schema 版本**：`cache_key()` 加入 `CACHE_SCHEMA`（当前 `v3`）；今后字段增删必须递增，避免旧缓存以缺字段形态继续命中、掩盖解析缺陷。
- **验证**：修复后首次实跑（DeepEP 2026-11-18，fast，22,127 in / 1,005 out，缓存命中 21,888）即产出 **5 张经验卡**，均含适用边界与反模式；无需新增第二次 LLM 调用（原计划的 rule 提取小调用取消）。
- **周期**：`config.yaml` 的 `auto_chain.analysis_interval_days` 由 7 改为 **1**（每日分析），`abstract_interval_days` 保持 7；代码默认值不变（仍为 7，旧配置行为不变）。
- **配额**：`depth.weekly_quota.fast` 由 3 调整为 **5**（`strong` 仍 1），配合每日分析加速积累样本；按 ¥0.05/次估算，上限约 ¥0.25/周。设计方案 §11 同步升为 v1.6。

## [Unreleased] - 2026-11-19 · 报告模板 v3（架构学习版）

- **模板落盘**：`docs/报告模板-v3.md`（结构/合同/权重/数据源映射/验收标准）与 `docs/报告模板-版本记录.md`（v1→v2a→v3 历史，旧版不删）。
- **渲染器 v3**：`render_report` 改为「导读 + 1 定位 / 2 架构全景 / 3 核心抽象 / 4 ADR / 5 扩展 / 6 经验卡 + 附录 A（证据索引与未知项）/ 附录 B（许可证·维护·工程·成本）」；正文区分 `[事实] / [判断] / [未获得]`，参数表全部下沉附录。
- **确定性新增**：`report.profile` 白名单（`architecture_learning` / `adoption_due_diligence` / `contributor_onboarding`，非法值 fail-fast）；注意力预算写入报告头；从源码切片扫描 `register/entry_points/plugin/adapter/backend/hook` 等模式，归一化去重后用于第 3/5 章；README/架构/贡献类文档分块注入第 1/2 章。
- **ADR 六字段**：决策 / 替代 / 代价 / 证据 / 可复用规则 / 边界·反模式；`InsightItem` 增加 `rule` / `boundary`（旧缓存缺字段自动为空并标注未获得）。
- **测试 200 → 211**：新增 `tests/test_report_v3.py`（档位白名单 / 头部声明 / ADR 六字段 / 经验卡边界 / 模式扫描确定性与过滤 / 序列化兼容）。
- **实测**：DeepEP `2026-11-18` 重跑为 v3 实例（fast，22,127 in / 865 out，含 21,888 缓存命中，约 ¥0.013）；6 条 ADR 均带真实 `README.md:N` 证据。
- **已知局限**：fast 模型三次尝试仍未输出非空 `rule`/`boundary`，经验卡按设计留空并写明原因（不用通用建议充数）；后续需 strong 档或独立提取轮次。

## [Unreleased] - 2026-11-18 · 报告 v2a（可读性重构）

- **报告结构 v2a**：`render.py` 改为「导读 + 6 个阅读模块（定位 / 许可 / 架构 / 工程 / 维护 / 扩展）+ 附录 A–E」；正文以文字叙述为主，运行元数据、特征卡、体检事实、洞见表、外部资料下沉到附录。许可证/依赖链/CI/issue 等未采集项明确写「未采集 + 原因」，不编造。
- **兼容**：既有 11 份报告仍为旧五区块格式，站点可正常渲染；新生成的报告使用 v2a。`D10_WORDING`、成本异常块、`- 架构范式标签：` 行保持不变，站点解析不受影响。
- 测试 199 → **200**（新增 v2a 可读性守护）；锚文件 v1.10 → **v1.11**；`CODEBUDDY.md` v1.16 → **v1.17**；`docs/执行手册.md` §4 报告结构同步更新。
- **DeepEP v2a 实例**：`analyze --depth fast --as-of 2026-11-18` 生成 `reports/deepseek-ai__DeepEP__2026-11-18.md`（8036 字符；旧 11-03 strong 报告 4939 字符、洞见仅 10%）。本次输入 21,930 tok / 输出 410 tok，¥0.0469；同 as-of 重跑命中缓存 ¥0。新报告 domain 自动归为 `ai_infra`，README 摘要已去 Markdown/链接噪声。

## [Unreleased] - 2026-11-17 · 独立周期 + 时间线归档

- **周期解耦**：新增 `auto_chain.analysis_interval_days` / `abstract_interval_days`，分别控制自动分析与抽象的最小真实调用间隔；缺省继承旧键 `min_interval_days`（默认 7），旧配置不改行为不变。`auto_interval_reached()` 支持 `days` 参数，workflow 两段各传各的值。
- **站点时间线**：新增 `timeline.html`，按报告 `as-of` 的年月分组并链接到完整报告，导航加入「时间线」入口；产物 22 → **23**，仍零 JS / 零 CDN / 零网络。
- 测试 197 → **199**（独立周期 +1 / 时间线 +1）；锚文件 v1.9 → **v1.10**；`CODEBUDDY.md` v1.15 → **v1.16**。

## [Unreleased] - 2026-11-17 · 抽象链路闭合 + 站点视觉升级

**范围**：修复规律库首条无法生成的 S4 缺陷 · 强化证据格式提示与重试 · 授权冒烟真跑产出 3 条 L1 · 静态站点视觉重构。本轮 3 次真实抽象调用合计 ¥0.0085。

### 新增 / 修复

- **S4 add-op 准入修复**：`ops_from_items()` 不再无条件丢弃 `chose=add`；只有 `owner/repo|file:line`、repo ∈ 本次真实样本、行号合法时才构造带真实代码证据的 L1 条目（`source=real`）。`ModelResult` 增加 `raw_items`，缓存 key 升级 v2，簇内/跨域编排均按真实样本复核后合并 ops。
- **证据格式闭环**：抽象 prompt 明确 `evidence=owner/repo|path:line` 并注入真实特征卡的文件行作为候选；格式不合规自动纠正重试一次，usage 累计计入台账。警告文案不再出现「判废：ok」自相矛盾。
- **规律库首批条目**：授权临时阈值 5 冒烟真跑（跑完恢复 6），run `c43d3a8ae4f71995` 状态 `completed`，产出 **3 条 L1**（P-001~P-003，均带 lmdeploy 的真实 `file:line`）。`patterns/library.yaml` 不再为 `[]`。
- **静态站点视觉升级**：统一设计系统（深色渐变导航 + 卡片网格 + 统一表格容器 + 响应式），新增各页导言块与首页数据卡片；保持零 JS / 零外部 CDN / 零网络 / 确定性输出。
- 测试 192 → **197**（抽象修复 +5）；锚文件 v1.8 → **v1.9**；`CODEBUDDY.md` v1.14 → **v1.15**。

### 已知局限

- 首批 3 条 L1 无反例位、自检 `可下钻到代码证据：否`（L2 门槛未达）；`ai_infra` 簇 3 个样本、`onnxruntime` 未归类；L2 ≥15 / L3 ≥5 / L4 ≥1 仍远未达成。

## [Unreleased] - 2026-11-16 · 审查整改（A 级 + B1/B2/B4）

**范围**：注释与文案校准 · 快照元数据 90 天 gzip 归档 · `site --check --strict` 接入 CI · E13 追加。本轮零真实模型调用。

### 新增

- **快照保留（B1）**：`retention --snapshots-only` 把超 `retention.snapshot_keep_days`（默认 90 天）的 `data/snapshots/<repo>/<date>.json` **原地** gzip 为 `.json.gz`；gzip 头时间固定为 0（字节确定）、解压字节校验通过才删源、重复执行幂等。`load_snapshot` 兼容 `.json.gz`（`--as-of` 语义不变）；`pool.yml` 在 dirty 守卫后调用，归档结果随真源同批提交。
- **站点严格核验（B2）**：`site --check --strict` 在有差异时退出 1（缺省仍 0）；`auto.yml` 的 `auto-site` 改用 strict，站点漂移从此会让定时任务变红。`--strict` 脱离 `--check` 使用按参数错误（2）处理。

### 变更

- **测试 186 → 192**（+3 快照归档 / +2 strict / +1 pool workflow 守卫）：`test_l2` 17、`test_l4` 24、`test_workflow_pathspec` 3。
- **文档校准（A 级）**：`CODEBUDDY.md` §4.1 的 respx 表述改为实际保护（清空凭据 + 禁用 external + 传输层间谍）；CLI `--help` 描述 L2 → L4；README/CODEBUDDY 退出码 1 措辞统一；`pool.dedupe` 标注"当前无消费者"。
- **E13（B4）**：`docs/经验固化.md` 追加「分段验收通过 ≠ 端到端需求闭合」，关闭 D49 #55。

## [Unreleased] - 2026-11-15 · 路径 B 自动化 + 文档体系刷新

**范围**：自动链自动化落地 · 成本告警三通道 · 治理决策（外部 LLM 退出开发）· 全仓文档事实刷新。本轮零真实模型调用、`costs.jsonl` 11 行不变、¥0。

### 新增

- **路径 B 自动链**（`.github/workflows/auto.yml`）：三段独立 job（`auto-analyze` / `auto-abstract` / `auto-site`），真实调用间隔由 `auto_chain.min_interval_days`（默认 7，可配置）控制，分析段与抽象段各自独立闸门、各查各的 `purpose` 锚点；锚点随真源跨运行持久化（`.gitattributes` `merge=union` + `scripts/auto_persist.sh` 并行安全回写）。
- **成本异常三通道**：报告头部区块 / Actions `::warning` / 站点红色 badge，统一 `render.COST_ANOMALY_MARKER == site._ANOMALY_MARKER` 标记一致性守护（单侧改动即失败）；`::warning` 仅在 `analyze` 路径命中时输出，`cost` 子命令为查询、不扩告警、不新增口径。**只标注、不阻断**。
- 测试 157 → **186**（路径 B 自动化新增 29 条）；`site/` 20 → **22 产物**；`ruff format` 53 files、mypy 16 source、`validate_workflow.py` 13/13、`site --check` 一致，门禁六连全绿。

### 校验 / 校准

- `auto.yml` 首个 `event=schedule` run `43618367472` 已获得（`created_at` `2026-11-14T16:56:51Z` = 北京 2026-11-15 00:56:51 周日），落在低谷半价便宜时段；按「真实 API 调用是否落便宜时段」口径判**无便宜时段偏移**，cron 候选值 `0 11 * * *` 未改；`pool.yml` 的 `17 3 * * *` 与实测约 8 小时差仅留证据、不外推、不改 cron。

### 治理 / 文档

- **治理决策（项目负责人 2026-11-15）**：外部 LLM 退出项目开发，方案设计 / 任务卡制定 / 代码开发 / 文档维护全由本 Agent 负责 —— 落盘 `CODEBUDDY.md` §0-A + 锚文件 §8.2 附记 + 会话记忆。
- **本质诉求口径纠正**：核心是「保证输出质量前提下把控成本」，非零 LLM 一刀切；成本把控 = 成本闸门 / 异常告警 / 可回溯账单 / 低谷时段调度整套工程。
- 锚文件 v1.6 → **v1.7**（§8.2 ② 0 条 → 恰 2 条 L3、③ 157 → 186、⑥ 20 → 22 产物 / 哈希不硬编码 / schedule 已获得；D53 待定措辞保留）；文档维护日志 v1.31 → **v1.32**（补路径 B 章节）；CODEBUDDY.md → **v1.12**；README / 功能总览 / 开发日志 / 成本预算同步计数与能力。
- 远端 `main` 每日由 `chore(pool)`/`chore(auto)` 自动提交前移，文档不再硬编码哈希、以 `git rev-parse origin/main` 自取为准；远端 tag 0，本地 `l0`–`l5` 冻结未动。

## [Unreleased] - 2026-11-08 · 实现轮 v1.0（D50 Q1–Q8 落地）

**范围**：cron 恢复 · `retention` 生产接线 · 跨域抽象 · `paradigm_tags` · 纯静态前端三能力 · 文档回填 · 一次端到端演练。本轮 **¥0**（端到端 `analyze --depth off`，零 LLM）。

### 新增

- `retention` CLI 生产命令（默认 dry-run；`--apply` 才归档；`protected_paths` 白名单含 `site/`、`external/`、三 jsonl、`patterns/`、`reports/`、`config.yaml`）。
- 跨域抽象 `abstract --cross`：独立入口（不与簇内 run 混排），消费 `cross_domain_min_l2_entries`（8）与 `cross_domain_every_cluster_runs`（4），`TYPE_CROSS_DOMAIN` 投入使用，run 记录沿用九字段，`budget_gate` / `off` / `CachedModelCaller` 同样生效。
- `paradigm_tags`：`llm.py` 受控词表 + `Insight.paradigm_tags`，同步 prompt / 校验 / 缓存键（schema 版本随 system 文本变化自动失效）；报告「洞见」段新增「架构范式标签」行。
- 站点纯预生成三能力（零脚本 / 零外部 JS·CDN / 零网络）：`search.html` + `search-index.json`（关键词检索）、`tags.html`（按 `paradigm_tags` 静态分组）、`compare.html`（2–3 张特征卡并排）；`index.html` nav 与首页表补入口。产物 15 → **19**（端到端演练新增 1 份报告页后为 **20**）。
- 新增测试：`test_retention_cli.py`（2）· `test_cross_domain.py`（9）· `test_paradigm_site.py`（10）；全量 136 → **157**。

### 变更

- `.github/workflows/pool.yml`：按 D50/Q3 恢复 `on.schedule`（原 cron `17 3 * * *` 原文保留），`workflow_dispatch` 并存；删除「cron 待 Gate 3 授权」旧注释。
- `scripts/validate_workflow.py`：第 1 项断言由「不含 schedule」反转为「含 schedule」（真实断言，非恒真）；仍 13/13。
- 文档回填：`README.md` / `CODEBUDDY.md` / `docs/功能总览.md` / `CONTRIBUTING.md` / `config.yaml`（版本引用 v1.3 → v1.5）。

### 说明

- **D18 = A 不翻案**：D31 run #2 Success 只证明调度链路通，不改 L2 收口结论。
- `patterns/library.yaml` 仍为 `[]`；`abstract` / `abstract --cross` 真实运行仍为 `insufficient_samples` 空态（不伪造条目、不降阈值）。
- 远端 tag 仍 **0**；本地 `l0`–`l4` 未移动。

## [Unreleased] - 2026-11-08 · D31 发布接线（#1 Failure → 补丁轮 #2 Success）

**发布接线**：建私有仓库 / remote / 首次 push `main`（`6748b0a`）；**不推 tag**（远端 tag = 0）、不 force、不启用 cron。

### 实测

- `git push -u origin main`：514 objects / 1.56 MiB；`main...origin/main` 建立；远端仅 `refs/heads/main`。
- 真实 Actions run `42450787839`（run_number 1 / attempt 2；attempt 1 亦 failure）：**Failure**；失败 step「提交真源并推送」0s / exit 128；`fatal: pathspec 'data/ledger' did not match any files`。
- 成功 step「追加观测」：7 个仓库 `pool add` 全部 exit 0；远端未前进（无 bot 提交）。
- 限流响应头：**未获得 + 原因**（步骤未输出/采集 `x-ratelimit-*`）。

### 根因与修复

- 根因：Git 不跟踪空目录；`data/ledger/` 无 tracked 文件（`git ls-tree` 为空），本地因 `init.ensure_skeleton()` 留有空的 `data/ledger/`，CI fresh checkout 不物化 → `git add -- data/ledger` pathspec 不匹配。与 `.gitignore` 无关；`pool add` 不写 ledger（`selected_jsonl` 无写入方）。
- 修复草案（**未落地**，新缺陷轮次）：移除 `data/ledger` pathspec，或 `git add` 前 `mkdir -p data/ledger`。

### 说明

- **D18 = A 不翻案**：真实 run 不改变「降级静态校验即 L2 收口」结论，仅登记新缺陷。
- **cron 未启用**；Gate 3 单独授权。本轮 ¥0，`costs.jsonl` 零改动；不推 tag。

### 补丁轮（2026-11-08，pathspec 修复）

- **修复**：workflow `git add -- data/pool data/ledger data/snapshots` → `git add -- data/pool data/snapshots`（方案 ① 最小移除）；注释改为接线约束；`scripts/validate_workflow.py` 的「真源路径覆盖」项同步适配（13/13）。
- **反向用例**：`tests/test_workflow_pathspec.py`（2 条）—— clean tree 缺 `data/ledger` 时旧 pathspec 必 fatal、当前 workflow pathspec 必 exit 0；全量 134 → **136**。
- **真实重跑 #2**：run `42455959308`（run_number 2 / attempt 1）**Success**；06:44:16–06:45:03Z（≈47s）；步骤 1–8 全 success；`git add -- data/pool data/snapshots` → bot commit `ac5d16a`（8 files / 180,805 insertions）→ `bb52f09..ac5d16a main -> main`。
- **缺陷关闭**：`data/ledger` pathspec 修复在真实 CI 上验证通过；远端 tag 仍 **0**；本地 `l0`–`l4` 未移动。
- **Gate 3 状态**：由「事实不满足、明确不得启用」变为「**待单独授权**」（仍不自动启用）；cron 未启用。
- **D18 = A 不翻案**：真实 run 只是补验证据，不追溯改 L2 收口结论。
- 限流响应头 **未获得 + 原因**（日志无 `x-ratelimit-*`）；本轮 ¥0，`costs.jsonl` 零改动；不推 tag。

## [Unreleased] - 2026-11-07 · 收尾（未打 tag）

**全景定稿**：无代码改动，零 LLM / 零网络 / 本阶段增量成本恒 ¥0。

### 新增

- `docs/功能总览.md`：七部分全景 —— ① 五阶段能力与 tag / hash ② 命令总表 ③ 真源 / 派生基线 / 可再生缓存三层布局（对齐设计方案 **v1.5 §8.2**）④ 文档地图（Agent 侧 vs 负责人侧）⑤ 成本总账（¥0 路径 + 真实调用 + 账外 ping）⑥ 已知局限七项 ⑦ 六锚点与文档体系约定；数字均可回溯到已提交文件与 tag
- `docs/经验固化.md` 末尾追加**结构化索引**（E1–E12：编号 / 主题 / 适用阶段），既有条目未改

### 核对

- `docs/数据源手册.md` §10.6 D19 分栏**只核对未重写**：A/B/C 三环境并存、互不覆盖、无「源不可用 / 已证明可达」断言、反爬特征仍未获得；不新增片段、不补仓库名或 star 数
- `docs/开发日志.md` 记「Chat 侧臆测已撤回，Agent 侧归档不变」
- `CODEBUDDY.md`：§8 同步设计方案 v1.5 §8.2（`site/` = 可重建派生基线，入库）、§9 增「收尾 ✅」、§10 `docs/功能总览.md` 改为「已建」

### 实测

- 门禁四连：**134 passed** / `ruff check` / `ruff format --check` / `mypy strict`（16 source files）
- `site --check` 一致（15 个产物，未写盘）；`data/costs/costs.jsonl` 相对 `l4` **零改动**
- 真实 key 零命中（`git grep` 三类白名单逐条归类：环境变量名 / 测试夹具假值 / 文档与第三方源码术语）

### 已知限制 / 未做

- 规律库仍空、L3 深层能力仅单测、5 张特征卡缺源码证据、workflow 未真实调度、设计方案 §5 三项前端能力未实现、价格复核未做、D19 附件正文未获得 —— 详见 `docs/功能总览.md` §6
- **D31 全部延后**（remote / push / cron / 真实 Actions run）；**本轮不打 tag**

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
