# CODEBUDDY.md

> **项目名**：`osslens`（包名 / CLI 名 / 目录名统一，路径 `~/projects/osslens`）
> **本文件是 AI Agent 在本仓库工作的入口。每次动手前先读。**
> **生成方**：项目负责人（一次性，Chat 只生成一次）；**维护方**：**Code Agent**（**自维护**：内容有变即直接改，不需逐次授权）。
> **维护约束**：唯一约束 = `docs/经验库-冲突与覆盖清单.md` §8.2 **六锚点不得漂移**；改后 `git diff -- CODEBUDDY.md` 逐项核对，锚点丢失按该 §8.2 从 SSOT 回填。
> **上游 SSOT**：`docs/设计方案.md`（what/why）· `docs/执行手册.md`（how）· `docs/文档维护日志.md`
> **当前版本**：v1.6 · **对应 tag**：`l2` · **日期**：2026-11-05

---

## 0. 工作方式（先看这个）

1. **你是执行者**，项目负责人是决策者。**每个里程碑结束后停下**，输出验收报告，不要开始下一阶段。
2. **不要全量读 SSOT**。读项目负责人**点名的章节**；常用点名见 §6。
3. **不确定的列出来问**，不要自作主张。发现文档冲突 → **停下 + 引双方原文上报**，不得自行按低优先级文档执行。
4. **一次只做一件事**；给项目负责人的待确认项 **≤1 个**。
5. **全程中文回复**（技术术语、代码、路径除外）。

**权威顺序**：`任务卡 > 本文件 > 执行手册 > 设计方案 > 其他文档`
★ **高优先级 ≠ 正确**：它只决定"听谁的"，不决定"谁是对的"。任务卡与 SSOT 冲突 → 停下上报。

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
python -m osslens init               # 初始化工作区骨架
python -m osslens pool add <owner/repo> [--channel hot|classic|watchlist]
python -m osslens pool list          # 按通道分别打分排序
python -m osslens pool eligible      # 深挖候选（热点需过观察期）
python -m osslens analyze <owner/repo> [--depth auto|off|fast|strong] \
        [--channel ...] [--domain ...] [--as-of ISO] [--dry-run] [--no-ledger]
python -m osslens abstract           # 规律抽象（批量触发）
python -m osslens cost [--as-of ISO] # 成本台账
python -m osslens site               # L4 静态站点
```

### 2.1 开发命令（build / lint / test / 单测）

```bash
pip install -e ".[dev]"        # 装含 pytest / ruff / mypy / respx 的开发依赖；setuptools 后端，无独立 build 步骤（`build` 未装）
osslens --help                 # 或 python -m osslens；pyproject.toml [project.scripts] 入口

pytest                         # 全量 76 例（含 tests/test_l2.py 14 条）
pytest tests/test_core.py::test_report_is_byte_identical   # 单测（node id）
pytest tests/test_l1.py -k "context or probe_blocked"     # 按关键字筛
pytest -m "not network"        # 离线；pyproject.toml 定义 network marker，当前无用例带此标记
pytest --cov=osslens --cov-report=term-missing            # 覆盖率（pytest-cov 在 dev 依赖）

ruff check . && ruff format --check .   # lint + 格式（line-length 100；排除 data/ reports/ site/）
ruff format .                  # 自动格式化
mypy                           # strict，files = ["osslens"]（13 个源文件），不走 tests/

pytest && ruff check . && ruff format --check . && mypy    # §7 门禁四连（全绿才可提交）
```

`ruff` 的 `select` / `extend-exclude`、`mypy strict` 的口径都在 `pyproject.toml`，改配置先改那里；
`tests/conftest.py` 默认清空凭据环境变量并以 `OFFLINE_OVERRIDES` 关闭外部探测（单测不发网络请求）。

**环境变量**：`GITHUB_TOKEN` · `OSSLENS_LLM_API_KEY` · `OSSLENS_LLM_BASE_URL`
（名称由 `config.yaml` 的 `github_token_env` / `llm.*_env` 指定，**代码不硬编码**）

★ **实现进度（L2 / tag `l2`，2026-11-05）**：已实现 `init` · `pool add|list|eligible` · `analyze` · `cost`；
`abstract`（L3）与 `site`（L4）**尚未实现**。
`analyze` 支持 `off` · **`fast`（deepseek-flash，thinking 关）** · **`strong`（deepseek-v4-pro，thinking 开，已实跑）**。
模型/thinking/输出上限按档位配置：`config.yaml → llm.models / llm.thinking / llm.max_output_tokens`；`api_key`/`base_url` 缺任一即降级 `off`。
闸门按 `估算 × budget.estimate_safety_factor(1.3)` 判断；报告成本行带 D10 口径字样。

**退出码契约**（★ 写死）：

| 码 | 含义 |
|---|---|
| **0** | 完成（**可能已降级**——降级在报告元数据块与 `costs.jsonl` 中可见） |
| 1 | 配置错误 |
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
| `osslens/patterns.py` | 规律库求值、召回三分类 | `test_three_class_output` / `test_not_applicable_when_domain_mismatch` |
| `osslens/pool.py` | 入池、打分、观察期 | 打分与观察期测试 |
| `osslens/render.py` | 报告渲染（MD）、`D10_WORDING` 常量 | `test_report_is_byte_identical` / `test_report_carries_d10_wording_and_five_sections` |
| `osslens/llm.py` | LLM 客户端、结构阶梯、判废、结果缓存、上下文裁剪、`Usage.reasoning_tokens` | `test_llm_*` / `test_context_drops_sources_when_over_budget` |
| `osslens/prompts.py` | 分档 prompt 常量（**代码资产，不放 docs**）：`FAST_INSIGHT_SYSTEM` / `STRONG_INSIGHT_SYSTEM` | `test_llm_success_parses_usage`（断言首级 `json_object`、thinking 关闭） |
| `osslens/retention.py` | T5 缓存层保留策略（白名单分层 + 内容寻址去重 + 按期归档） | `test_l2.py::test_apply_dedupes_and_never_touches_sources` |
| `osslens/webui.py` | L4 静态站点 | L4 阶段 |

### 3.1 大图：一次 `analyze` 的数据流（跨模块，改代码前先看这个）

```text
cli.py:_cmd_analyze (cli.py:334) ── 唯一编排入口，串起全链路
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
  ├─ depth.py:estimate_cost + llm.Usage → CostLine
  └─ render.py:render_report → 报告 MD                          # 五区块固定顺序；atomic_write_text 落盘
       退出码恒 0（降级 / 配额 / 预算 / 未配 key 均 0）

pool 链：cli._cmd_pool_* → pool.observe（pool.jsonl append-only）→ score_channel（hot/classic/watchlist 不混排）
        → evaluate_eligibility（观察期 3–7 天；打分只排序、绝不升档）
cost 链：cli._cmd_cost → depth.load_events / summarize（util.start_of_week / start_of_month 窗口）
横切：util.py —— HttpClient（限速/重试/UA）、FixedClock / SystemClock、stable_json / sort_paths / r4（幂等）、
      atomic_write_text、read_jsonl / append_jsonl（真源 append-only）。改它必须跑全套（见上表）。
```

设计层大图见 `docs/总体架构设计.md` §2（五段工作流）/ §3.1（分层）——补充件、非 SSOT，冲突以设计方案为准。

★ `patterns.py` / `webui.py` **L0 尚未创建**（L3 / L4 才建）；当前包内 **11 个业务模块 + 2 个入口 = 13 个 .py**：
`cli` · `config` · `util` · `collect` · `featcard` · `depth` · `llm` · `pool` · `prompts` · `render` · `retention` + `__init__` / `__main__`（`mypy` 报 13 source files）。

**幂等/契约测试**（`tests/test_core.py`，**不得删，只能加**）：

| 测试 | 阶段 | 仓库现状 |
|---|---|---|
| `test_report_is_byte_identical` · `test_as_of_dominates` · `test_stable_json_is_sorted` | L0 | ✅ 已存在 |
| `test_no_llm_involved` · `test_no_credentials_falls_back_to_off` | L0 | ✅ 已存在 |
| `test_quota_downgrade_is_recorded` · `test_budget_gate_cannot_be_overridden` · `test_manual_override_bypasses_quota_but_not_budget` | L0 | ✅ 已存在 |
| `test_template_page_is_a_miss` · `test_real_content_is_a_hit` | L1 | ✅ 已存在（`tests/test_l1.py`，用 `docs/ref/` 真实片段） |
| `test_strong_is_available_and_maps_to_pro_model_with_thinking` · `test_safety_factor_blocks_l1_underestimate` · `test_report_carries_d10_wording_and_five_sections` · `test_apply_dedupes_and_never_touches_sources` | L2 | ✅ 已存在（`tests/test_l2.py`，含「故意让它失败」反向用例） |
| `test_three_class_output` · `test_not_applicable_when_domain_mismatch` | L3 | ⬜ **待建，当前不存在**（`patterns.py` 未实现） |

> ★ 目前仅 L3 的两条是**目标清单**（`patterns.py` 未建）。L1 的两条已落地，L2 的 14 条已落地。
> `tests/test_l1.py` 共 23 条、`tests/test_l2.py` 共 14 条，**全仓 76 条**：证据回查、Mermaid 幂等、预算/M7 反向、LLM 阶梯与判废、探测 fail-closed、strong 接线、四层跨周、安全系数、D10、保留策略。
> 核对命令：`pytest --collect-only -q | grep -E "three_class|not_applicable"`（**应无输出**，L3 两条待建）；
> `pytest --collect-only -q | grep -E "template_page|real_content"`（**应仅输出 2 条 L1**，不得为 0）。

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
| 报告结构 | 执行手册 附录 A |
| 验收模板 | 执行手册 §6 |
| 总体架构 / 端到端流程 / 技术选型 | `docs/总体架构设计.md` §2 / §3 / §4（补充件，非 SSOT） |
| 开发命令 / 门禁四连 | 本文件 §2.1 · `CONTRIBUTING.md` |
| 快照保留策略（D15 / T5） | 设计方案 §8.2（唯一权威）· `docs/数据源手册.md` §10.3 · `osslens/retention.py` |
| trending / 限流实测（T6） | `docs/数据源手册.md` §10.1 / §10.2 |
| 定时建池 workflow（T7） | `.github/workflows/pool.yml` · `scripts/validate_workflow.py` |
| 已知账外支出（③′） | `docs/成本预算.md` §0（**不是台账，不参与 `cost` 统计**） |

---

## 7. 每阶段收尾必做

- [ ] 门禁全绿：`pytest && ruff check . && ruff format --check . && mypy`（见 §2.1）
- [ ] 追加 `docs/开发日志.md` 本阶段章节（实测、决策依据、坑）
- [ ] 更新本文件（若内容有变）
- [ ] 提交前列 `git status` 确认；核对 `git ls-files | grep -E '\.env$|secrets|\.db$'` 为空
- [ ] **提交 + 打 tag**（如 `l0`），再通知项目负责人刷新文档
- [ ] 输出验收报告（八段，在会话输出**不落成文件**），**停下**

★ **禁止 force 更新 tag**；`l0` = 792894d、`l1` = 289beed **冻结、不得移动**（见 `docs/执行手册.md` / `docs/文档维护日志.md`）。`l2` 为本阶段新增 tag，同样冻结；新 tag 由项目负责人定（N7）。

**验收报告八段**：`已完成 / DoD 核对 / 关键文件清单 / 测试与覆盖率 / 真实运行证据 / 遇到的坑与解决 / 待决策问题（≤1）/ 下一步`

★ **真实运行证据必须非空**（单测通过 ≠ 功能真的产出过内容）；
★ **诚实暴露局限**比漂亮的完成度有价值。

---

## 8. 数据布局（真源 vs 可丢弃）

```
config.yaml                                        # 唯一配置真源
patterns/*.yaml                                    # 规律库（真源，可 diff）
data/
├── ledger/selected.jsonl                          # ★ 真源 append-only：何时选过、为什么选
├── pool/pool.jsonl                                # ★ 真源 append-only + 观测序列
├── costs/costs.jsonl                              # ★ 真源 append-only：调用/降级/预算事件
├── snapshots/<owner>__<repo>/<date>.json           # 采集快照元数据 + sha256
│   ├── src/                                       # 源码切片 + manifest.json（可再生缓存）
│   └── external/                                  # ★ deepwiki.json + source.txt + sha256（不可再生真源）
├── featcards/<owner>__<repo>__<commit>.json        # 可再生
├── llm_cache/<sha256>.json                        # 可再生（丢了只多花钱，不丢事实）
├── cache_objects/<sha2>/<sha256>                  # 可再生索引（内容寻址去重，.gitignore 忽略）
└── cache_archive/                                # 可再生归档（按期归档，.gitignore 忽略）
reports/<owner>__<repo>__<date>.md                  # ★ 真源
site/                                              # L4 静态站（可丢弃、可重建）
```

**★ 按可再生性分层（D15，唯一权威 = `docs/设计方案.md` §8.2 v1.3）**：

| 路径 | 归类 | 规则 |
|---|---|---|
| `patterns/` · `data/ledger` · `data/pool` · `data/costs` · `reports/` | **真源** | append-only；删除先列清单 + 停下等确认 |
| `data/snapshots/**/external/`（deepwiki.json / source.txt / sha256） | ★ **不可再生真源** | 外部索引状态错过不可复现，带来源四元组（红线 #13）→ **不删、不覆盖** |
| `data/snapshots/**/src/`（源码切片 + manifest.json） | **可再生缓存** | 按 commit 从 codeload tarball 可重拉 → 可丢弃、可去重、可归档清理 |
| `data/featcards/` · `data/llm_cache/` · `site/` · 任何 DB 索引 | **可再生缓存** | 可丢弃、可重建 |

★ **红线 #6 的 append-only 清单只含 3 个 jsonl + `patterns/`，从未含 `data/snapshots` 整块**
→ 清理 `src/` / `llm_cache/` **不违规**；`docs/成本预算.md` §4 作为证据层与本表不冲突（D15 已对齐）。
★ **推翻判据**：若 codeload tarball 不再按 commit 可重拉（仓库被删 / 私有化）→ `src/` 升格为真源（见设计方案 §8.2）。

---

## 9. 里程碑

| 阶段 | 目标 | 完成判据 |
|---|---|---|
| **L0** | 采集 + 建池 + 去重 + **off 档体检报告** | 对 1 个真实仓库跑出完整体检报告（**零 LLM**） |
| **L1** | 特征卡 L0 + 依赖图 + 外部工具（fail-closed）+ fast 档 | 特征卡含证据；Mermaid 可渲染 |
| **L2** ✅ | strong 档 + 四层跨周联动 + 估算安全系数 + 成本闭环 + 快照保留 + 定时建池 | strong 实跑（¥0.4174 / 5 条带证据洞见）；同 as-of 重跑字节一致；76 测试 |
| **L3** | 模式召回 + 批量抽象 + 反例自动挖掘 | 积累 ≥5 个项目后触发首次抽象 |
| **L4** | 静态站点（只读） | 由 MD + JSON 生成，无后端 |

> ★ L2 局限：`github.com/trending` 未获得（TCP 超时）；actionlint 未安装走降级静态校验，**不等同于 GitHub 真实 run**；未 push、未建 remote。详见 `docs/开发日志.md` L2 章节。

---

## 10. 你还要维护的文档

| 文档 | 建的时刻 | 状态（2026-11-04） |
|---|---|---|
| `README.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | L0 首个 tag | ✅ 已建成 |
| `docs/开发日志.md` | L0 验收后（按时间记事实、实测、坑） | ✅ 已建成（开发者每阶段收尾追加） |
| `docs/数据源手册.md` | L0 验收后（**归并已有实测文件，不新造**） | ✅ 已建成 |
| `docs/成本预算.md` | **L1 首次真实调用后**（L0 期间无真实花费，不建） | ✅ 已建成 |
| `docs/经验固化.md`（工程侧） | 攒够第一条工程教训 | ✅ 已建成（E1–E8） |
| `docs/经验库-冲突与覆盖清单.md` | 外部经验库裁决（项目负责人维护） | ✅ 已建成（v1.2，§8.2 六锚点唯一权威） |
| `docs/总体架构设计.md` | 补充件（端到端流程 / 技术选型 / 路线图） | ✅ 已建成（v0.4） |
| `docs/功能总览.md` | 收尾 | ⬜ **唯一待建** |

★ **不预建空文档**。★ **数据源手册用已有实测材料归并**：
`外部工具命中率实测_推理Infra组.md` / `_Agent训练组.md` / `watchlist星标活跃度复核.md` / `_meas/token_result.json`
★ `docs/总体架构设计.md` 是**补充件、非 SSOT**（只答 SSOT 未答的端到端流程 / 技术选型 / 路线图）；与 `docs/设计方案.md` 不一致 → **以设计方案为准**并回报。

---

## 11. 外部经验库（只读参考）

| 文件 | 用法 |
|---|---|
| `docs/经验库-冲突与覆盖清单.md` | ★ **新会话开工前必读**（已裁决冲突，约 4KB） |
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
