# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

> **项目名**：`osslens`（包名 / CLI 名 / 目录名统一，路径 `~/projects/osslens`）
> **本文件是 AI Agent 在本仓库工作的入口。每次动手前先读。**
> **生成方**：项目负责人（一次性，Chat 只生成一次）；**维护方**：**Code Agent**（**自维护**：内容有变即直接改，不需逐次授权）。
> **维护约束**：唯一约束 = `docs/经验库-冲突与覆盖清单.md` §8.2 **六锚点不得漂移**；改后 `git diff -- CODEBUDDY.md` 逐项核对，锚点丢失按该 §8.2 从 SSOT 回填。
> **上游 SSOT**：`docs/设计方案.md`（what/why）· `docs/执行手册.md`（how）· `docs/文档维护日志.md`
> **当前版本**：v1.19 · **对应 tag**：`l5` · **日期**：2026-11-19（v1.19：报告模板 v3 落地（导读 + 6 章 + 附录 A/B）· `report.profile` 白名单 · 架构模式扫描 · 209 tests；v1.18：DeepEP v2a 实例报告（24 产物）· domain 自动归类修复；v1.17：报告 v2a（导读 + 6 阅读模块 + 附录）· 200 tests；v1.16：分析/抽象周期独立配置（`analysis_interval_days` / `abstract_interval_days`）· 站点时间线归档（23 产物 / 199 tests）；v1.15：抽象 add-op 修复 + 证据格式重试真跑产出 3 条 L1 · 站点视觉升级 · 测试 197；v1.14：B1 快照 90 天 gzip 归档 · B2 `site --check --strict` 接入 auto-site · B4 追加 E13；v1.13：§2.1 补充 `.venv` 运行口径；v1.12：全仓挥发性事实刷新 157→186 / v1.6→v1.7 / 20→22 产物 / schedule 已获得、三套版本号口径说明；v1.11：新增 §0-A 治理决策）

---

## 0. 工作方式（先看这个）

### 0-A 最新治理决策（2026-11-15，★ 最高优先，覆盖下文相悖旧条文）

> **项目负责人 2026-11-15 决策（任务卡级，权威顺序最高）**：
>
> 1. **外部 LLM 退出开发**：后续**外部 LLM（Chat 助手等）不参与本项目开发**。
>    **方案设计、任务卡制定、代码开发、文档维护全部由本 Agent（CodeBuddy Code）负责**，
>    不再由外部 LLM 生成 / 审阅 / 覆盖，也不再"停下等 Chat 出任务卡 / 出全量 SSOT"。
> 2. **本质诉求（纠正"零 LLM 一刀切"误读）**：项目核心是**在保证输出质量的前提下把控成本**，
>    **不是**"零 LLM 能做的绝不用 LLM"这种一刀切；深度分析本身就需要调用 LLM。
>    成本把控是一项**细节且复杂**的工程，至少含四件套：① **成本闸门**（周配额 / 周·月·单次 run token 预算 /
>    安全系数，`config.yaml → depth.budget`）② **异常告警**（报告头部 / Actions `::warning` / 站点红 badge，
>    **只标注不阻断**）③ **历史成本账单可追踪可回溯**（`data/costs/costs.jsonl` append-only 真源 + `cost` 命令）
>    ④ 把 **LLM API 调用排在供应商空闲低谷时段**（DeepSeek 低谷约为高峰半价 = "免费的午餐"，
>    见 `docs/成本预算.md` §1）。不得把"跑 off 档 / 真实调用少 / 压低 LLM 使用"当成目标或优点，
>    也不得把"规律库空 / 深度能力未验证"包装成"成本控制做得好"。
>
> **优先级（覆盖下列旧条文中"外部 LLM 参与 / Agent 只读 / 停下上报"的归属语义；旧条文原文保留不改，六锚点不得漂移）**：
>
> - §0 第 1、3 条、§0「自维护范围」、§4.1 红线 #1、§10 文档清单、§11 中的
>   "三份 SSOT / 锚文件由**项目负责人（Chat 助手）维护**、**Agent 只读**、**待负责人升版**、
>   **发现冲突停下引双方原文上报**、**任务卡由 Chat 出**"等**归属与上报**表述，自本决策起不再适用：
>   这些文件的维护责任归本 Agent，过期事实 / 冲突对齐直接改、改后按 §8.2 核对六锚点，不再因"这是负责人文件"而停工。
> - **不变的**：§4 全部 12+8 条**技术红线**（off 档零请求、fail-closed、append-only、幂等、降级双写、
>   打分不升档、只标注不阻断 等）、六锚点不得漂移、`docs/ref/` 禁读，以及
>   remote / push / tag / cron / 可见性等**意图性动作仍停下交回项目负责人（人）裁决**（N4）。
>   本决策转移的是**产出与维护责任**，不转移意图性决策的最终裁决权。
> - **范围**：本决策 = 落盘该决策 + 今后文档维护归属变更，**不等于**授权一次性重写全部历史 SSOT 正文；
>   历史文档按需、逐类 commit 更新（N6，一个 commit 一类改动）。
>
> **`/clear` + `/init` 存活（本决策必须跨会话持续生效，不得回退旧口径）**：
>
> - 已同步写入会话记忆（`MEMORY.md` → `project_governance` / `feedback_essential_need`），`/clear` 后自动注入。
> - `/init` 会改写本文件：改写后按 §8.2 做 `git diff -- CODEBUDDY.md` 审阅时，**§0-A 为必核 / 必回填项**
>   （见锚文件 §8.2 附记）；若被稀释或删除，从会话记忆 / 本卡回填，
>   **不得**以"恢复旧工作方式"为由回退到"外部 LLM 参与开发 / Agent 只读文档"。

1. **你是执行者**，项目负责人是决策者。**每个里程碑结束后停下**，输出验收报告，不要开始下一阶段。
2. **不要全量读 SSOT**。读项目负责人**点名的章节**；常用点名见 §6。
3. **不确定的列出来问**，不要自作主张。发现文档冲突 → **停下 + 引双方原文上报**，不得自行按低优先级文档执行。
4. **一次只做一件事**；给项目负责人的待确认项 **≤1 个**。
5. **全程中文回复**（技术术语、代码、路径除外）。

**权威顺序**：`任务卡 > 本文件 > 执行手册 > 设计方案 > 其他文档`
★ **高优先级 ≠ 正确**：它只决定"听谁的"，不决定"谁是对的"。任务卡与 SSOT 冲突 → 停下上报。
★ **外部经验库是建议，不是规格**：与本项目红线冲突 → 以红线为准；C1/C2 裁决与 N1–N12 见 §11。
★ **自维护范围**：`CODEBUDDY.md` 与 §10 的 README / CONTRIBUTING 等文档由 Agent 直接改、不需逐次授权（见文件头「维护方」）；只读/禁改的只有锚文件 `docs/经验库-冲突与覆盖清单.md`（负责人维护、Agent 只读）与红线 #1 的三份 SSOT。前者过期引用/冲突对齐属自维护，后者才停下引双方原文上报。
★ **引用与挥发性状态**：本文件内 `file:line` 是近似值，以符号名为准；测试条数 / tag 哈希 / cron 状态 / run 编号等以 `docs/经验库-冲突与覆盖清单.md §8.2`（第 6 类事实性陈述）为唯一权威，本文件仅速查；改后 `git diff -- CODEBUDDY.md` 逐项核对六锚点。
★ **本文件较长**：约束文件尾部最易被截掉；开工按 N2 `grep -n "红线\|必须\|不得" CODEBUDDY.md` 核对硬约束，务必读到 §11 结尾。

---

## 1. 项目是什么

一个**低成本、可长期运行**的开源项目深度分析系统：
建候选池 → 人选定 → 分档分析 → 产出可核验的单项目报告 → 周期横向抽象成规律库。
终极目标不是"一堆漂亮报告"，而是**量变到质变**：让项目负责人掌握架构范式、设计套路与技术选型能力。

**因此，下面三条是这个项目的灵魂，任何改动都不能破坏：**

| # | 灵魂条款 |
|---|---|
| 1 | **低成本优先**：零 LLM 能做的绝不用 LLM；档位与预算是成本闸门 |
| 2 | **可核验**：每条判断必须带代码证据（file:line）；拿不到就写"未获得 + 原因"，**禁止编造** |
| 3 | **量变到质变**：规律库靠增量 merge 积累，不靠单篇报告的漂亮程度 |

---

## 2. 命令与运行

```bash
pip install -e .                     # 或 python -m osslens
osslens --version                    # 版本号；pyproject.toml [project.scripts] 入口
python -m osslens init               # 初始化工作区骨架
python -m osslens pool add <owner/repo> [--channel hot|classic|watchlist] [--as-of ISO]
python -m osslens pool list [--as-of ISO] [--json]          # 按通道分别打分排序
python -m osslens pool eligible [--as-of ISO] [--json]      # 深挖候选（热点需过观察期）
python -m osslens analyze <owner/repo> [--depth auto|off|fast|strong] \
        [--channel ...] [--domain ...] [--as-of ISO] [--dry-run] [--no-ledger] [--no-sources]
python -m osslens cost [--as-of ISO] [--json]   # 成本台账
python -m osslens abstract [--as-of ISO] [--cluster ID] [--cross] [--off] [--dry-run] [--json]
                                        # L3 规律抽象（S1 阈值 / run 记录 / 零 LLM 召回；--cross = 跨域 run，独立入口不与簇内混排）
python -m osslens retention [--as-of ISO] [--apply] [--snapshots-only] [--json]
                                        # T5 保留策略（dry_run 默认）；--apply 归档 src/ 与 llm_cache/；
                                        # --snapshots-only 只做快照元数据 gzip（超 retention.snapshot_keep_days）
python -m osslens site [--out DIR] [--as-of ISO] [--check] [--strict]
                                        # L4 静态只读站点（零 LLM / 零网络 / ¥0；当前 24 产物，含 search/tags/compare/timeline）
```

全局参数 `--root DIR`：所有子命令共用，指定工作区根目录（默认当前目录，见 `osslens/cli.py` 顶层 `common` 解析器）。

### 2.1 开发命令（build / lint / test / 单测）

```bash
pip install -e ".[dev]"        # 装含 pytest / ruff / mypy / respx 的开发依赖；setuptools 后端，无独立 build 步骤（`build` 未装）
osslens --help                 # 或 python -m osslens；pyproject.toml [project.scripts] 入口

pytest                         # 全量 209 例（200 + 报告 v3 守护 9；含 test_core 22、test_l3 43、test_report_v3 9）
pytest tests/test_core.py::test_report_is_byte_identical   # 单测（node id）
pytest tests/test_l4.py -k "check or empty"               # 按关键字筛
pytest -m "not network"        # 离线；pyproject.toml 定义 network marker，当前无用例带此标记
pytest --cov=osslens --cov-report=term-missing            # 覆盖率（pytest-cov 在 dev 依赖）

ruff check . && ruff format --check .   # lint + 格式（line-length 100；排除 data/ reports/ site/）
ruff format .                  # 自动格式化
mypy                           # strict，files = ["osslens"]（16 个源文件），不走 tests/
python scripts/validate_workflow.py   # T7 workflow 降级静态校验（13 项 PASS，替代未安装的 actionlint）

pytest && ruff check . && ruff format --check . && mypy    # §7 门禁四连（全绿才可提交）
```

★ **用仓库自带 `.venv` 跑**：仓库根已有 `.venv/`，系统解释器不一定装了 dev 依赖。先 `source .venv/bin/activate`
（或直接用 `.venv/bin/python -m pytest`），上面的 `pytest` / `ruff` / `mypy` / `python -m osslens` 全部在同一虚拟环境里执行；
否则会出现「装了依赖却 import 失败」或 `site --check` 用到另一份旧包。

★ **三套版本号互不相关，勿「对齐」**：`pyproject.toml` 的 `version = "0.5.0"` 是**包发布版本**；本文件头的 `v1.13` 是**文档版本**（随事实刷新递增）；README / CHANGELOG 里的「实现轮 v1.0」是**阶段轮次名**。三者命名空间不同，把包版本「对齐」成 1.0 或把文档版本当包版本都是误读。

`ruff` 的 `select` / `extend-exclude`、`mypy strict` 的口径都在 `pyproject.toml`，改配置先改那里；
`tests/conftest.py` 默认清空凭据环境变量并以 `OFFLINE_OVERRIDES` 关闭外部探测（单测不发网络请求）。
★ `mypy` 的 `files = ["osslens"]`（`pyproject.toml:58`）不含 `scripts/`（也不含 `tests/`）；
`ruff check .` / `ruff format --check .` 按路径发现文件（`extend-exclude` 仅排 `data/` `reports/` `site/`，`:47`），`scripts/` 在 lint 范围内，`src` 只影响 import 解析、不限制检查范围 → 改 `scripts/` 下脚本时门禁四连的 mypy 侧不覆盖。

**测试分布（209 条）**：`test_core.py` 22（L0 幂等/契约）· `test_report_v3.py` 9（v3 结构/ADR/经验卡/档位）· `test_l1.py` 23（探测/特征卡/Mermaid）·
`test_l2.py` 17（档位/预算/D10/保留/快照归档）· `test_collect.py` 7（快照/源码切片）· `test_pool.py` 7（打分/观察期）·
`test_time.py` 4（跨周/跨月时序）· `test_l3.py` 43（召回/四层 schema/ops/编排/成本闸门/S4 add 准入）·
`test_l4.py` 25（站点四块/空态/`--check`/`--strict`/幂等/零网络/成本红 badge/时间线）·
`test_auto_chain.py` 28（自动链间隔/闸门/归因/告警/标记守护/独立周期）·
`test_workflow_pathspec.py` 3 · `test_retention_cli.py` 2（T1）· `test_cross_domain.py` 9（T2）·
`test_paradigm_site.py` 10（T3）。
按领域改代码时优先跑对应文件，收尾仍须门禁四连。
★ 锚文件 §8.2 已同步为 **v1.13 / 全仓 209**（2026-11-19，依 §0-A 由本 Agent 维护升版；② 恰 2 条 L3、③ 157 → 209、④ 快照 `.json.gz` 归档、⑥ 24 产物 / 哈希不硬编码 / schedule 已获得）。本文件与锚文件口径一致，**无待上报差异**。

**环境变量**：`GITHUB_TOKEN` · `OSSLENS_LLM_API_KEY` · `OSSLENS_LLM_BASE_URL`
（名称由 `config.yaml` 的 `github_token_env` / `llm.*_env` 指定，**代码不硬编码**）

★ **实现进度（截至 v1.12 / tag `l5`，2026-11-15）**：已实现 `init` · `pool add|list|eligible` · `analyze` · `cost` ·
`abstract`（L3：零 LLM 三态召回 / 四层 schema / ops 增量 merge / reconcile / 反例挖掘 / 成本闸门 / run 记录）·
`site`（L4：静态只读站点 / `index.md` / 四块呈现 / `--check` / 零 LLM·零网络·¥0）·
`retention` · `abstract --cross` · `paradigm_tags` · 静态三能力 · 路径 B 三段自动链。
各阶段完成判据见 §9（收尾 / D31 / 实现轮 v1.0 / 路径 B 均已 ✅），本节只列当前能力，不复述历史状态。
★ **路径 B 自动化（2026-11-12→14，已 push `main`）**：`schedule` 仅作低成本检查，真实调用间隔由
`auto_chain.analysis_interval_days` / `abstract_interval_days` 分别控制（缺省继承 `min_interval_days`=7）；两段各自闸门、各查各的 `purpose` 锚点；
锚点随 `data/costs` 回写并跨运行保留（`.gitattributes` → `merge=union`，`scripts/auto_persist.sh`
负责「提交→rebase→合并后重建站点→push 重试」的并行安全回写）；成本异常三通道
（报告头部区块 / Actions `::warning` / 站点红色 badge）均只标注、不阻断。
★ 规律库首批条目已由**授权冒烟真跑**产出：3 条 L1（真实 `file:line` 证据，`source=real`），阈值已恢复为 6；样本未达 S1 阈值时仍 `insufficient_samples` 产 0 条，站点如实展示，不伪造条目。
★ 收尾动作（`docs/功能总览.md` / 经验汇总 / 价格复核 / remote / push / 真实 Actions run）原为 L4 卡外单独一轮，**现已在 D31 / 实现轮 v1.0 / 路径 B 三轮完成**（见 §9）；此处保留仅为说明演进，**不再是待办**。
`analyze` 支持 `off` · **`fast`（deepseek-flash，thinking 关）** · **`strong`（deepseek-v4-pro，thinking 开，已实跑）**。
模型/thinking/输出上限按档位配置：`config.yaml → llm.models / llm.thinking / llm.max_output_tokens`；`api_key`/`base_url` 缺任一即降级 `off`。
闸门按 `估算 × budget.estimate_safety_factor(1.3)` 判断；报告成本行带 D10 口径字样。

**退出码契约**（★ 写死）：

| 码 | 含义 |
|---|---|
| **0** | 完成（**可能已降级**——降级在报告元数据块与 `costs.jsonl` 中可见） |
| 1 | 配置错误 / 运行错误（引擎错误、中断） |
| 2 | 参数错误 |

> ★ **可选源失败、配额耗尽、预算拦截、未配 key 一律退出码 0**。非 0 只能是真失败。

---

## 3. 模块地图（改哪 → 跑什么）

| 文件 | 职责 | 改了要跑 |
|---|---|---|
| `osslens/cli.py` | 参数解析、子命令分发、错误兜底 | `pytest tests/` |
| `osslens/config.py` | 配置加载与默认值（`DEFAULT_CONFIG`） | `pytest tests/` + 确认新增项进 `config.yaml` |
| `osslens/util.py` | HTTP / sha256 / 排序 / 原子写 / JSONL 读写 / `r4` | **全套**（排序变更会影响幂等） |
| `osslens/collect.py` | GitHub 快照、**源码切片**（codeload tarball）、**外部工具探测** `probe_external` | `test_template_page_is_a_miss` / `test_real_content_is_a_hit` / `test_probe_blocked_page_is_fail_closed` |
| `osslens/featcard.py` | 特征卡 L0 提取、`depgraph_mermaid` | 特征卡证据测试 + Mermaid 渲染检查 |
| `osslens/depth.py` | **档位四层 + 预算闸门 + Ledger** | `test_no_credentials_falls_back_to_off` / `test_quota_downgrade_is_recorded` / `test_budget_gate_*` |
| `osslens/patterns.py` | L3 规律库：零 LLM 三态召回（硬 gating + 加权 Jaccard）、四层条目 schema 校验、ops 增量 merge、反例挖掘、自检四问、真源纯净闸 | `pytest tests/test_l3.py` |
| `osslens/abstract.py` | L3 编排：`cluster_run` / reconcile / **`cross_domain_run`（Q5，独立 `--cross` 入口，消费 L2 条目数 + 簇内 run 数阈值）**、run 记录九字段、成本闸门、同输入缓存 | `pytest tests/test_l3.py` / `tests/test_cross_domain.py` |
| `osslens/site.py` | L4 静态只读站点：MD→HTML、四块呈现、纯 MD `index.md`、空态诚实、`site --check`、Q2 静态三能力（检索 / 范式标签 / 并排对比） | `pytest tests/test_l4.py` / `tests/test_paradigm_site.py` |
| `osslens/pool.py` | 入池、打分、观察期 | 打分与观察期测试 |
| `osslens/render.py` | 报告渲染（MD）、`D10_WORDING` 常量 | `test_report_is_byte_identical` / `test_report_carries_d10_wording_and_modules` / `test_report_v3.py` |
| `osslens/llm.py` | LLM 客户端、结构阶梯、判废、结果缓存、上下文裁剪、`Usage.reasoning_tokens`；`PARADIGM_TAGS` 受控词表 + `Insight.paradigm_tags`（Q7） | `test_llm_*` / `test_context_drops_sources_when_over_budget` / `tests/test_paradigm_site.py` |
| `osslens/prompts.py` | 分档 prompt 常量（**代码资产，不放 docs**）：`FAST_INSIGHT_SYSTEM` / `STRONG_INSIGHT_SYSTEM`（含 paradigm_tags schema，进 cache_key） | `test_llm_success_parses_usage`（断言首级 `json_object`、thinking 关闭） / `tests/test_paradigm_site.py` |
| `osslens/retention.py` | T5 缓存层保留策略（白名单分层 + 内容寻址去重 + 按期归档）；生产入口 `retention` CLI（dry_run 默认，`--apply` 才清理；`--snapshots-only` 供定时建池做快照 gzip；`protected_paths` 含 `site/`） | `test_l2.py::test_apply_dedupes_and_never_touches_sources` / `tests/test_retention_cli.py` |

### 3.1 大图：一次 `analyze` 的数据流（跨模块，改代码前先看这个）

```text
cli.py:_cmd_analyze ── 唯一编排入口，串起全链路
  ├─ config.py:Config.load → Layout            # 唯一配置真源 config.yaml + ${ENV} 环境变量
  ├─ collect.py:load_snapshot / fetch_snapshot → RepoSnapshot   # GitHub REST 6 端点，统一走 util.HttpClient
  ├─ collect.py:load_sources / fetch_sources → SourceBundle      # codeload tarball 源码切片（可再生缓存）
  ├─ featcard.py:build_featcard → 特征卡 JSON                   # 确定性提取：证据 / 语言占比 / 依赖图 Mermaid
  ├─ collect.py:probe_external → ExternalProbe                  # fail-closed：正文含 ≥3 个仓库真实路径才算命中
  ├─ cli.py:_build_context → llm.py:assemble_context → Context # 调用前裁剪（预估 → 组装 → 校验）
  ├─ depth.py:resolve_depth → DepthDecision                     # 通道基线 → 周配额 → 预算闸门
  │      AVAILABLE_DEPTHS = {"fast", "strong"}；L3 闸门按 估算×estimate_safety_factor(1.3) 判断
  │      降级 → build_ledger_event / record_event 双写 costs.jsonl
  ├─ cli.py:_run_insight（按档位取 model/thinking/purpose/max_tokens）
  │      → llm.py:LlmClient.chat_json                            # 结构阶梯 → 判废 → data/llm_cache 缓存
  ├─ depth.py:estimate_cost + llm.Usage → render.py:CostLine
  └─ render.py:render_report → 报告 MD                    # v3：导读 + 6 章 + 附录 A/B；atomic_write_text 落盘
       退出码恒 0（降级 / 配额 / 预算 / 未配 key 均 0）

pool 链：cli._cmd_pool_* → pool.observe（pool.jsonl append-only）→ score_channel（hot/classic/watchlist 不混排）
        → evaluate_eligibility（观察期 3–7 天；打分只排序、绝不升档）
cost 链：cli._cmd_cost → depth.load_events / summarize（util.start_of_week / start_of_month 窗口）
abstract 链（L3）：cli._cmd_abstract → abstract.cluster_run
  ├─ patterns.load_library（patterns/library.yaml 真源）+ abstract.load_samples（data/featcards/*.json 真实样本）
  ├─ config.domain_for → domain.id 主簇（归类缺口上报，不自行补规则）
  ├─ patterns.recall（零 LLM 三态）→ 反例候选池 → patterns.build_self_check 自检四问
  ├─ 样本 < abstract.cluster_min_new_projects → insufficient_samples（0 条 / 0 次 LLM / 合法终态）
  ├─ 否则 depth.compute_quota + config.safety_adjusted 闸门 → blocked / off 降级 / 模型调用（同输入缓存）
  ├─ patterns.apply_ops（六类 ops，falsified 不删）→ assert_storable → save_library + append_ops
  └─ append_run（data/abstract/runs.jsonl 九字段 append-only）+ record_event（costs.jsonl 记账）
site 链（L4）：cli._cmd_site → site.build_site（纯内存，只读真源）
  ├─ 输入：reports/*.md · data/featcards/*.json · patterns/library.yaml · costs.jsonl · abstract/runs.jsonl
  ├─ 产物：site/index.md（纯 MD 索引）· index.html · reports.html · featcards.html · patterns.html
  │        · costs.html · runs.html · report-<stem>.html（6 模块 + 附录顺序不变）
  ├─ --check：只比对不写盘，差异清单 + 默认退出码 0；--strict（CI 用）有差异退 1；正常 site 逐文件打印 新增/更新/未变
  └─ 零 LLM/零网络：不构造 HTTP 客户端；时间只来自 --as-of 或真源派生；产物不含绝对路径/运行时间戳
横切：util.py —— HttpClient（限速/重试/UA）、FixedClock / SystemClock、stable_json / sort_paths / r4（幂等）、
      atomic_write_text、read_jsonl / append_jsonl（真源 append-only）。改它必须跑全套（见上表）。
自动化层（路径 B，跨文件；改代码前先看这个）：
  .github/workflows/pool.yml ── T7 定时建池（cron `17 3 * * *`；零 LLM；dirty 守卫 → 按路径 add → bot 提交 → push）
  .github/workflows/auto.yml ── 三段独立 job，彼此无 needs（auto-analyze / auto-abstract / auto-site）
        ├─ 频率闸门：`auto_chain.analysis_interval_days` / `abstract_interval_days` 各自独立；各查各的 purpose 锚点
        ├─ auto-analyze / auto-abstract 回写真源 → scripts/auto_persist.sh（提交→rebase→合并后重建 site→push 重试）
        └─ auto-site 只读：python -m osslens site --check（不写盘 / 退出码 0）
  scripts/validate_workflow.py ── pool.yml 降级静态校验（13 项；命令见 §2.1，mypy/门禁四连不覆盖 scripts/）
```

设计层大图见 `docs/总体架构设计.md` §2（五段工作流）/ §3.1（分层）——补充件、非 SSOT，冲突以设计方案为准。

★ `webui.py` **未创建**：L4 按卡实现为 `site.py`（静态渲染 + CLI），无独立 webui 模块。
当前包内 **14 个业务模块 + 2 个入口 = 16 个 .py**：
`cli` · `config` · `util` · `collect` · `featcard` · `depth` · `llm` · `pool` · `prompts` · `render` · `retention` · `patterns` · `abstract` · `site` + `__init__` / `__main__`（`mypy` 报 16 source files）。

**幂等/契约测试**（`tests/test_core.py`，**不得删，只能加**）：

| 测试 | 阶段 | 仓库现状 |
|---|---|---|
| `test_report_is_byte_identical` · `test_as_of_dominates` · `test_stable_json_is_sorted` | L0 | ✅ 已存在 |
| `test_no_llm_involved` · `test_no_credentials_falls_back_to_off` | L0 | ✅ 已存在 |
| `test_quota_downgrade_is_recorded` · `test_budget_gate_cannot_be_overridden` · `test_manual_override_bypasses_quota_but_not_budget` | L0 | ✅ 已存在 |
| `test_template_page_is_a_miss` · `test_real_content_is_a_hit` | L1 | ✅ 已存在（`tests/test_l1.py`，用 `docs/ref/` 真实片段） |
| `test_strong_is_available_and_maps_to_pro_model_with_thinking` · `test_safety_factor_blocks_l1_underestimate` · `test_report_carries_d10_wording_and_five_sections` · `test_apply_dedupes_and_never_touches_sources` | L2 | ✅ 已存在（`tests/test_l2.py`，含「故意让它失败」反向用例） |
| `test_three_class_output` · `test_not_applicable_when_domain_mismatch` | L3 | ✅ 已存在（`tests/test_l3.py`，含「故意让它失败」反向用例） |
| `test_site_builds_full_static_site` · `test_empty_patterns_state_is_honest` · `test_site_check_reports_diff_without_writing` · `test_site_zero_network_transport_interception` | L4 | ✅ 已存在（`tests/test_l4.py`，含「故意让它失败」反向用例） |

> ★ L3 两条目标清单已落地（`patterns.py` / `abstract.py` 建成）；L4 站点契约测试 20 条亦已落地。L1 的两条、L2 的 14 条亦已落地。
> `tests/test_l1.py` 共 23 条、`tests/test_l2.py` 共 17 条、`tests/test_l3.py` 共 43 条、`tests/test_l4.py` 共 25 条、`tests/test_auto_chain.py` 共 28 条、`tests/test_report_v3.py` 共 9 条，**全仓 209 条**（实现轮 157 + 路径 B 自动化 29 + 审查整改 6 + 抽象修复 5 + 独立周期/时间线 2 + 报告 v2a 1 + 报告 v3 9）。
> 核对命令：`pytest --collect-only -q | grep -E "three_class|not_applicable"`（**应输出 2 条 L3**）；
> `pytest --collect-only -q | grep -E "template_page|real_content"`（**应仅输出 2 条 L1**，不得为 0）。
> ★ 锚文件 `docs/经验库-冲突与覆盖清单.md` 已同步为 **v1.13**（2026-11-19，依 §0-A 由本 Agent 维护升版）：§8.2 ②「恰 2 条 L3」、③「全仓 209」、④ 快照 `.json.gz` 归档、⑥ 24 产物 / 哈希不硬编码 / `event=schedule` 已获得。锚点 ③ 是**状态型**事实，随阶段推进刷新、**不得把已 ✅ 存在的测试重置为「⬜ 待建」**（第 4 类锚点语义不变）。
> 若后续发现锚文件状态落后于仓库现实 → 依 §0-A 由本 Agent 直接同步升版，改后按 §8.2 核对六锚点（不再「停下上报等负责人」）。

---

## 4. 红线（违反即返工）

### 4.1 最高 12 条

| # | 红线 |
|---|---|
| 1 | **不改 `docs/设计方案.md` / `docs/执行手册.md` / `docs/文档维护日志.md`**（项目负责人出全量并覆盖） |
| 2 | **off 档严禁任何 LLM 调用**；断言必须是"代码根本没发请求"，不是"mock 顶掉后断言 0" |
| 3 | **无凭据不报错**：缺 api_key / base_url / model 任一 → 降级 `off`，**退出码 0** |
| 4 | ★ **外部资料 fail-closed**：判定用「正文是否含 ≥3 个仓库内真实路径」，**不用"能否访问"**；未命中 → 标注「不可用（未索引）」，**绝不回退成模板化页面** |
| 5 | ★ **无证据不入特征卡**：`parallel.hits` / `cache.hits` / `hardware.*` 的每个 `true` 必须带 evidence（file+line+snippet）；带不出就置 `false` |
| 6 | **真源 append-only**：`data/ledger/selected.jsonl` / `data/pool/pool.jsonl` / `data/costs/costs.jsonl` 只追加；`patterns/` 只追加修订（旧 ID 保留 alias）。**任何删除先列清单 + 停下等确认** |
| 7 | **禁止 `git clean -fd`** |
| 8 | ★ **幂等：时间不来自运行时钟**。报告时间 = `--as-of`；未传取输入快照 `fetched_at`，**不是 `datetime.now()`** |
| 9 | ★ **幂等：集合必须确定性排序**（路径升序；计数值降序 + 路径升序 tie-break）；浮点 `round(x,4)`；JSON `sort_keys=True` |
| 10 | ★ **降级必须双写留痕**：报告头部「运行元数据」块 + `costs.jsonl` 追加一条。**静默降级 = 失控** |
| 11 | ★ **召回零 LLM 且必须三分类**（采用 / 未采用=反例候选 / 不适用）。**无反例位的模式条目禁止入库** |
| 12 | ★ **打分只用于排序，绝不用于升档**（自己造的指标决定自己花多少钱 = 循环论证） |

> ★ #2 的**静态侧守门**：`tests/test_core.py::test_llm_endpoint_only_in_llm_module` 断言模型端点字面量
> （`chat/completions` / `api.openai.com` / `api.anthropic.com` / `generativelanguage`）只出现在 `osslens/llm.py`；
> `tests/test_l4.py::test_site_module_has_no_endpoint_literals_and_no_http_import` 守站点模块。
> 运行期默认**不发外发**：`tests/conftest.py` 的 `_no_credentials` 清空 `GITHUB_TOKEN` / `OSSLENS_LLM_*`，
> `OFFLINE_OVERRIDES` 关闭 `external.deepwiki_enabled`；`test_no_llm_involved` 与
> `test_site_zero_network_transport_interception` 另在 `httpx.HTTPTransport.handle_request` 装间谍并断言
> `egress == []`（后者含反向探针，证明间谍本身有效）。
> ★ `respx` 虽在 dev 依赖（`pyproject.toml:22`），**当前用例未使用**；新增联网路径测试需拦截时，
> 显式引入 respx 或复用同一间谍写法，不要假设 conftest 已全局拦截。

### 4.2 项目特有 8 条

| # | 红线 |
|---|---|
| 13 | ★ **外部快照带来源四元组**：`source / url / fetched_at / sha256`；**结构分离**（原文与生成内容不混排） |
| 14 | ★ **上下文裁剪发生在调用之前**（预估 → 组装 → 校验），**绝不在生成中途降质** |
| 15 | ★ **prompt 是代码资产**：放 `src/*/prompts/` 或 `templates/`，**不放 docs**；改 prompt 触发对应单测 |
| 16 | ★ **LLM 输出必须紧凑**：只返回 `id + 字段`，**不回显标题/摘要**（会撞 max_tokens） |
| 17 | ★ **可证伪性由代码判定，不由 LLM 输出**。LLM 不得自己说"无法验证/无法判断" |
| 18 | ★ **不可证伪的洞察标注为「观点」**，不计入规律库统计 |
| 19 | ★ **测试断言不得打到注释/说明文字**（他项目两次踩中：脚注含"★"导致 `assert "★" in output` 恒真）。断言必须针对**真实输出结构** |
| 20 | ★ **时间驱动逻辑必须写跨天/跨月时序单测**（受控时钟推进）。只测当天 = 没测 |

### 4.3 工程类

| # | 红线 |
|---|---|
| 21 | **不引入 openai SDK**（httpx 直连；SDK 阻碍 mock） |
| 22 | **统一走 HttpClient**（限速/重试/代理/UA 复用） |
| 23 | **配置只从 `config.yaml` + 环境变量读**；环境开关用 `${ENV}` 占位符；**代码不硬编码阈值** |
| 24 | **mypy strict**：不用 `# type: ignore` 掩盖，必要时用 `cast` |
| 25 | **不用 `ubuntu-latest`**，固定 `ubuntu-24.04` |
| 26 | **禁止 force push**；push 前先 rebase |
| 27 | **不用"本地测不到"推断"源不可用"** —— 本地失败 → 加 `*_base_url` 配置项，不可达时 warning + 跳过 |
| 28 | **禁止伪造 fixtures**：抓不到就 `pytest.skip(reason=...)` 并写明原因 |

---

## 5. 三个最容易做错的坑

| 坑 | 错法 | 正解 |
|---|---|---|
| **外部工具未命中** | HTTP 200 就当命中 | 必须判定正文含 ≥3 个仓库内真实路径。**真实案例 OpenLake**：200 + 显示仓库名 + 正文零专属内容 |
| **档位降级** | 降级了没留痕 | 双写：报告元数据块 + `costs.jsonl` |
| **测试恒真** | `assert "★" in output` 打到脚注 | 断言针对真实输出结构，如 JSON 字段值 |

---

## 6. 常用 SSOT 章节点名

| 要做什么 | 读哪里 |
|---|---|
| 档位与配额 | 设计方案 §2、§11 |
| 特征卡 | 设计方案 §3 |
| 模式召回 | 设计方案 §4 + 规律库与范围配置 |
| 打分与入池 | 设计方案 §6.1–§6.4 |
| 依赖图 | 设计方案 §6.5 |
| 幂等 | 设计方案 §7 |
| 数据布局 / 真源分层（D15） | 设计方案 §8（**§8.2 为唯一权威**） |
| 成本观测 | 设计方案 §9 |
| 报告结构 | `docs/报告模板-v3.md`（导读 + 6 章 + 附录 A/B；`render.py` 与模板需同步） |
| 验收模板 | 执行手册 §6 |
| 总体架构 / 端到端流程 / 技术选型 | `docs/总体架构设计.md` §2 / §3 / §4（补充件，非 SSOT） |
| 开发命令 / 门禁四连 | 本文件 §2.1 · `CONTRIBUTING.md` |
| 快照保留策略（D15 / T5） | 设计方案 §8.2（唯一权威）· `docs/数据源手册.md` §10.3 · `osslens/retention.py` |
| trending / 限流实测（T6） | `docs/数据源手册.md` §10.1 / §10.2 |
| 定时建池 workflow（T7） | `.github/workflows/pool.yml` · `scripts/validate_workflow.py` |
| 已知账外支出（③′） | `docs/成本预算.md` §0（**不是台账，不参与 `cost` 统计**） |

★ **定时建池 workflow 接线约束**：`selected.jsonl` 接线时必须把 `data/ledger` **加回** `git add` pathspec，否则 CI 真源漏提交（出处：D31 run `42450787839` 的 `fatal: pathspec 'data/ledger'` 根因）；当前 `data/ledger` 无写入方，故不在 pathspec 内。

---

## 7. 每阶段收尾必做

- [ ] 门禁全绿：`pytest && ruff check . && ruff format --check . && mypy`（见 §2.1）
- [ ] 追加 `docs/开发日志.md` 本阶段章节（实测、决策依据、坑）
- [ ] 更新本文件（若内容有变）
- [ ] 提交前列 `git status` 确认；核对 `git ls-files | grep -E '\.env$|secrets|\.db$'` 为空
- [ ] **提交 + 打 tag**（如 `l0`），再通知项目负责人刷新文档
- [ ] 输出验收报告（八段，在会话输出**不落成文件**），**停下**

★ **禁止 force 更新 tag**；`l0` = 792894d、`l1` = 289beed **冻结、不得移动**（见 `docs/执行手册.md` / `docs/文档维护日志.md`）。`l2` = 787d8f5、`l3` / `l4` / `l5` 同样冻结（`l5`=6912add 本地、未推远端）；新 tag 由项目负责人定（N7）。

**验收报告八段**：`已完成 / DoD 核对 / 关键文件清单 / 测试与覆盖率 / 真实运行证据 / 遇到的坑与解决 / 待决策问题（≤1）/ 下一步`

★ **真实运行证据必须非空**（单测通过 ≠ 功能真的产出过内容）；
★ **诚实暴露局限**比漂亮的完成度有价值。

---

## 8. 数据布局（真源 vs 可丢弃）

```
config.yaml                                        # 唯一配置真源
patterns/
├── seed.yaml                                      # 种子（空列表）
├── library.yaml                                   # ★ 真源：规律库条目（只写真实样本产出，append-only）
└── ops.jsonl                                      # ★ 真源 append-only：ops 追加修订日志
data/
├── ledger/selected.jsonl                          # ★ 预留真源 append-only：何时选过、为什么选（当前尚空，无写入）
├── pool/pool.jsonl                                # ★ 真源 append-only + 观测序列
├── costs/costs.jsonl                              # ★ 真源 append-only：调用/降级/预算事件
├── abstract/runs.jsonl                            # ★ 真源 append-only：L3 run 记录（九字段）
├── snapshots/<owner>__<repo>/<date>.json           # 采集快照元数据 + sha256（超 90 天 → .json.gz，内容不变）
│   ├── src/                                       # 源码切片 + manifest.json（可再生缓存）
│   └── external/                                  # ★ deepwiki.json + source.txt + sha256（不可再生真源）
├── featcards/<owner>__<repo>__<commit>.json        # 可再生
├── llm_cache/<sha256>.json · abstract-<sha256>.json  # 可再生（丢了只多花钱，不丢事实）
├── cache_objects/<sha2>/<sha256>                  # 可再生索引（内容寻址去重，.gitignore 忽略）
└── cache_archive/                                # 可再生归档（按期归档，.gitignore 忽略）
reports/<owner>__<repo>__<date>.md                  # ★ 确定性 regenerate 产物（非 append-only，S2）
site/                                              # L4 静态站（★ 可重建派生基线，入库；index.md / index.html / 四块 + report-*.html）
```

**★ 按可再生性分层（D15，唯一权威 = `docs/设计方案.md` v1.5 §8.2）**：

| 路径 | 归类 | 规则 |
|---|---|---|
| `patterns/`（library.yaml / ops.jsonl）· `data/ledger` · `data/pool` · `data/costs` · `data/abstract/runs.jsonl` | **真源** | append-only；旧 ID 保留 alias；删除先列清单 + 停下等确认 |
| `reports/` | ★ **确定性 regenerate 产物**（S2 / 设计方案 v1.5 §8.2 精确化，**非 append-only**） | 同一 `(repo, as-of)` 换档位重跑**允许覆盖**：内容由快照 + 特征卡确定性重建，历史由 git tag 兜底；文件名 / 幂等键 / render / cli 路径均不变 |
| `site/`（当前 24 个产物，2026-11-18） | ★ **可重建的派生基线**（v1.5 精确化，**入库**，非真源） | 由 5 类真源确定性渲染；`site --check` 需与**已提交**基线比对；真源变更后须重跑 `site` 并提交，`--check` 给差异清单；**不得手写编辑产物**（D32=A） |
| `data/snapshots/**/external/`（deepwiki.json / source.txt / sha256） | ★ **不可再生真源** | 外部索引状态错过不可复现，带来源四元组（红线 #13）→ **不删、不覆盖** |
| `data/snapshots/**/src/`（源码切片 + manifest.json） | **可再生缓存** | 按 commit 从 codeload tarball 可重拉 → 可丢弃、可去重、可归档清理 |
| `data/featcards/` · `data/llm_cache/` · 任何 DB 索引 | **可再生缓存** | 可丢弃、可重建 |

★ **快照元数据保留窗口**：超 `retention.snapshot_keep_days`（默认 90 天）在**原地** gzip 为 `<date>.json.gz`；内容与 `sha256` 字段不变、解压字节校验后才删源、重复执行幂等；`load_snapshot` 兼容 `.json.gz`；仍属真源，不删除、不移动目录。

★ **实测形态（2026-11-07）**：`external/` 下为 `deepwiki.json`（`sha256` 是其内部字段，非独立文件）与 `source.txt`；探测未命中时不写 `source.txt`（6 个 external 目录仅 4 个有）。此处沿用 `docs/设计方案.md` v1.5 §8.2 的清单表述，`external/` **归类不变**。

★ **红线 #6 的 append-only 清单只含 3 个 jsonl + `patterns/` + `data/abstract/runs.jsonl`，从未含 `data/snapshots` 整块**
→ 清理 `src/` / `llm_cache/` **不违规**、覆盖 `reports/` **不违规**；`docs/成本预算.md` §4 作为证据层与本表不冲突（D15 已对齐）。
★ **推翻判据**：若 codeload tarball 不再按 commit 可重拉（仓库被删 / 私有化）→ `src/` 升格为真源（见设计方案 §8.2）。

---

## 9. 里程碑

| 阶段 | 目标 | 完成判据 |
|---|---|---|
| **L0** | 采集 + 建池 + 去重 + **off 档体检报告** | 对 1 个真实仓库跑出完整体检报告（**零 LLM**） |
| **L1** | 特征卡 L0 + 依赖图 + 外部工具（fail-closed）+ fast 档 | 特征卡含证据；Mermaid 可渲染 |
| **L2** ✅ | strong 档 + 四层跨周联动 + 估算安全系数 + 成本闭环 + 快照保留 + 定时建池 | strong 实跑（¥0.4174 / 5 条带证据洞见）；同 as-of 重跑字节一致；76 测试 |
| **L3** ✅ | 零 LLM 三态召回 + 四层抽象 + 增量 merge + 反例挖掘 + 抽象 run 成本闸门 | 链路端到端可运行（门槛/ops/反例/reconcile 均有断言）；**真实样本 5 < 簇内阈值 6 → `insufficient_samples` 产 0 条，首次真实抽象未触发**；114 测试 |
| **L4** ✅ | 静态只读站点（零后端 / 零 LLM / 零网络 / ¥0） | 由 MD + JSON 生成，无后端；15 个产物（当时）、`site --check` 一致、同 as-of 字节一致、空态如实、**本阶段 ¥0**；134 测试（当时） |
| **收尾** ✅ | 全景定稿：`docs/功能总览.md` / 经验固化结构化索引 / D19 口径定稿 / 文档回填 | 功能总览七部分齐全、数字可回溯；门禁四连全绿、`site --check` 一致；零 LLM / 零网络 / 本阶段 ¥0；收尾时未打 tag / 未 push（D31 后续已执行） |
| **D31 发布接线** ✅ | 私有远端可验证：私有空仓 / remote / push / 真实 Actions run | 建私有仓库 `tochikoma777/osslens`；只推 main（不推 tag，远端 tag 0）；run #2 `42455959308` **Success**；cron 当时未启用（Gate 3 待授权） |
| **实现轮 v1.0** ✅ | cron 启用 · retention 接线 · 跨域抽象 · paradigm_tags · 静态三能力 | 157 测试 / validate 13·13 / `site --check` 一致（20 产物）；端到端 ①→⑧ 各跑一次（run #3 Success / `pool eligible` 4 候选 / off 分析 / 抽象与跨域空态）；本地打 `l5` 不推远端 tag |
| **路径 B 自动化** ✅（本地） | 自动链 7 天间隔 · 抽象段同间隔/分锚点 · 锚点跨运行持久化 · 成本告警三通道 | 186 测试 / validate 13·13 / `site --check` 一致（22 产物）；真实调用 1 笔 ¥0.0278（run 43461199920）；`auto.yml` 首个 `event=schedule` run `43618367472` 已获得（2026-11-14T16:56:51Z = 北京周日 00:56，落便宜时段，判无便宜时段偏移，cron 候选值 `0 11 * * *` 未改） |

> ★ L2 局限（历史，D18=A 不翻案）：actionlint 未安装，走降级静态校验。D31 后已有真实 Actions run #2 Success（但只证明调度链路通，不等于 8 周无人值守自动编排已跑通）。
> ★ 发布状态：已建私有 remote `origin` 并 push `main`；D31 只推 main、远端 tag 0；本地 `l0`–`l4` 冻结、`l5` 本地打不推。
> ★ cron 状态：实现轮 v1.0 按 D50/Q3 授权恢复 `on.schedule`（`workflow_dispatch` 并存）；保留策略 `retention` 同步接线（Q6）。
> ★ D19 补采（2026-11-06，采集环境 B）：`github.com/` 首页与 `trending` **已 200 并归档三份真实片段**，见 `docs/数据源手册.md` §10.1.3；前次「未获得」仅为环境 A 本地 TCP 超时，**不是源不可用**。**反爬特征仍未获得**（未触发 ≠ 无反爬）。详见 `docs/开发日志.md` L2 / D19 章节。
> ★ L3 局限：`patterns/library.yaml` 仍为 `[]`（真源纯净，S4）；匿名 GitHub API 60/h 配额 + classic 入池门槛使同簇真实样本止于 5/6；抽象 run **未发生真实 LLM 调用**（¥0）；规律库条目、真实跨域 L3/L4 抽象、真实 reconcile 均待样本达标后验证。实现轮 v1.0 T2 已把跨域抽象**接线**（`abstract --cross` 消费 L2 条目数与簇内 run 数两阈值），但真实 L2 条目为 0 → 跨域 run 同样只能产出 `insufficient_samples` 空态。
> ★ L4 局限：`patterns/library.yaml` 仍为 `[]`，站点如实展示空态、不伪造条目；站点为只读快照，真源变动后需重跑 `site`（`--check` 给差异清单而非静默覆盖）；设计方案 §5 的「前端检索 / 标签过滤 / 并排对比」已按实现轮 v1.0 T3 以**纯预生成静态页**补实现（`search.html` / `tags.html` / `compare.html` + `search-index.json`，零脚本、零外部 JS/CDN、零网络；当前报告无 `paradigm_tags` 数据时标签页如实空态）；`costs.jsonl` 相对 `l3` 零改动。
> ★ D19 核查（2026-11-07，采集环境 C）：本轮终端 `api.github.com/` · `github.com/` · `github.com/trending` 均 200 并归档小片段，见 `docs/数据源手册.md` §10.6；与 §10.1 的环境 A 超时 / 环境 B 片段**分栏并存、互不覆盖**；**反爬特征仍未获得**（未触发 ≠ 无反爬）。本栏既不写「源不可用」也不写「已证明可达」。

---

## 10. 你还要维护的文档

| 文档 | 建的时刻 | 状态（2026-11-10） |
|---|---|---|
| `README.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | L0 首个 tag | ✅ 已建成 |
| `docs/开发日志.md` | L0 验收后（按时间记事实、实测、坑） | ✅ 已建成（开发者每阶段收尾追加） |
| `docs/数据源手册.md` | L0 验收后（**归并已有实测文件，不新造**） | ✅ 已建成 |
| `docs/成本预算.md` | **L1 首次真实调用后**（L0 期间无真实花费，不建） | ✅ 已建成 |
| `docs/经验固化.md`（工程侧） | 攒够第一条工程教训 | ✅ 已建成（E1–E13；E11 = D28 三态口径、E12 = HTML 转义断言、E13 = 分段验收 ≠ 端到端闭合） |
| `docs/经验库-冲突与覆盖清单.md` | 外部经验库裁决（项目负责人维护；旧归属表述依 §0-A 覆盖、原文保留） | ✅ 已建成（v1.13，2026-11-19 事实刷新：② 恰 2 条 L3 / ③ 全仓 209 / ④ 快照 gzip 归档 / ⑥ 24 产物 / 哈希不硬编码 / schedule 已获得；与仓库现实一致） |
| `docs/总体架构设计.md` | 补充件（端到端流程 / 技术选型 / 路线图） | ✅ 已建成（v0.5） |
| `docs/功能总览.md` | 收尾 | ✅ 已建成（2026-11-07，七部分全景定稿） |

★ **不预建空文档**。★ **数据源手册用已有实测材料归并**：
`外部工具命中率实测_推理Infra组.md` / `_Agent训练组.md` / `watchlist星标活跃度复核.md` / `docs/ref/token_result.json`
★ `docs/总体架构设计.md` 是**补充件、非 SSOT**（只答 SSOT 未答的端到端流程 / 技术选型 / 路线图）；与 `docs/设计方案.md` 不一致 → **以设计方案为准**并回报。

---

## 11. 外部经验库（只读参考）

| 文件 | 用法 |
|---|---|
| `docs/经验库-冲突与覆盖清单.md` | ★ **新会话开工前必读**（已裁决冲突；篇幅约 20KB，六锚点见 §8.2） |
| `docs/ref/经验库-执行版.md`（41KB） | **不必通读**；遇到具体问题时按章节检索 |
| `docs/ref/经验库-全量.md`（96KB） | **禁止全量读**（`cat` 即违规）；按《章节索引卡》定位后按章节 grep |
| `docs/经验库-章节索引卡.md` | 检索导航 |

**★ 权威顺序（写死）**
`任务卡 > 本文件 > 执行手册 > 设计方案 > 冲突与覆盖清单 > 经验库原文`

**★ 三条约束**
1. 经验库是**建议，不是规格**。与本项目红线冲突 → **以红线为准**，并在验收报告中列出冲突条目。
2. 两份 `docs/ref/` 下的文件**只读，不得修改**（不进 CHANGELOG、不进开发日志）。本项目的经验沉淀写 `docs/经验固化.md`（你自建自维护）。
3. 引用经验库条目时**注明来源章节**，便于回溯。

### 11.1 ★ 已裁决的两处冲突（必看，否则会做错）

| # | 冲突 | 裁决 |
|---|---|---|
| **C1** | 经验库 §6.5 定义 `1`=质量不达标；osslens 定义 `1`=配置错误 | **以 osslens 契约为准**（§2 退出码表）。质量不达标/配额耗尽/预算拦截/未配 key **一律退出码 0 + 留痕** |
| **C2** | 经验库 §7.15 说"降档最不推荐"；osslens 用档位控成本 | 不冲突：省钱顺位是**持久化 > 缩小范围 > 按条件跳过 > 降档**。**不要为省钱主动降档**；降档只在闸门触发时发生，且必须双写留痕 |

### 11.2 ★ 经验库新增纳入的 12 条（osslens SSOT 里没有的）

| # | 条目 |
|---|---|
| N1 | **文件路径 ≠ 交付**：沙盒/容器生成的文件对方访问不到，要么内联进回复，要么走可达通道 |
| N2 | **每轮开工前 grep 硬约束**：`grep -n "红线\|必须\|不得" CODEBUDDY.md`（约束文件尾部最易被截掉） |
| N3 | **有否决权**：掌握事实而指令与实际情况不符 → 直接反对并说明理由，不迁就执行 |
| N4 | **决策归属**：事实性问题你查并给证据；**意图性问题（要不要做/优先级/取舍）留给项目负责人** |
| N5 | **开工核对两项**：① 依赖闭合（依赖模块是真实现还是存根，有存根先补）② 命名核对（沿用已有代码定义的名字，指令只描述行为不指定名字） |
| N6 | **一个 commit 一类改动**，`git add -p` 按路径挑，**不用 `git add -A`** |
| N7 | **commit 编号归属项目负责人**，不自行编号 |
| N8 | **`git init` 与 `.gitignore` 必须同时做** |
| N9 | **gitignore 陷阱**：每行只写一个 pattern；`data/*.db` ≠ `*.db`；改完用 `git check-ignore -v` 验证 |
| N10 | **提交失败先怀疑 hook**：`pre-commit run --all-files --verbose`，**不用 `--no-verify`** |
| N11 | **脚本内 `git pull` 必须 `--ff-only`**；pull 前确认工作区干净，"脏就跳过"必须显式写出来 |
| N12 | **文档准生证三问**：① 回答什么问题 ② 谁能改 ③ 什么时候作废——第③问答不出的是过程文档，不入库 |
