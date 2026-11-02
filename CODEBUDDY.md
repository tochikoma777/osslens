# CODEBUDDY.md

> **项目名**：`osslens`（包名 / CLI 名 / 目录名统一，路径 `~/projects/osslens`）
> **本文件是 AI Agent 在本仓库工作的入口。每次动手前先读。**
> **生成方**：项目负责人（一次性）；**维护方**：**Code Agent**（内容有变即更新）。
> **上游 SSOT**：`docs/设计方案.md`（what/why）· `docs/执行手册.md`（how）· `docs/文档维护日志.md`
> **当前版本**：v1.3 · **对应 tag**：`l0` · **日期**：2026-11-02

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

**环境变量**：`GITHUB_TOKEN` · `OSSLENS_LLM_API_KEY` · `OSSLENS_LLM_BASE_URL`
（名称由 `config.yaml` 的 `github_token_env` / `llm.*_env` 指定，**代码不硬编码**）

★ **实现进度（L0 / tag `l0`，2026-11-02）**：已实现 `init` · `pool add|list|eligible` · `analyze` · `cost`；
`abstract`（L3）与 `site`（L4）**尚未实现**，`analyze` 目前只产出 `off` 档（fast/strong 属 L1）。
`config.yaml` 另有 `llm.model_env`（模型 ID），三件套缺任一即降级 `off`。

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
| `osslens/collect.py` | GitHub 快照、`used_by`、**外部工具探测** `probe_external` | `test_template_page_is_a_miss` / `test_real_content_is_a_hit` |
| `osslens/featcard.py` | 特征卡 L0 提取、`depgraph_mermaid` | 特征卡证据测试 + Mermaid 渲染检查 |
| `osslens/depth.py` | **档位四层 + 预算闸门 + Ledger** | `test_no_credentials_falls_back_to_off` / `test_quota_downgrade_is_recorded` / `test_budget_gate_*` |
| `osslens/patterns.py` | 规律库求值、召回三分类 | `test_three_class_output` / `test_not_applicable_when_domain_mismatch` |
| `osslens/pool.py` | 入池、打分、观察期 | 打分与观察期测试 |
| `osslens/render.py` | 报告渲染（MD） | `test_report_is_byte_identical` |
| `osslens/webui.py` | L4 静态站点 | L4 阶段 |

★ `patterns.py` / `webui.py` **L0 尚未创建**（L3 / L4 才建）；当前包内 10 个模块：
`cli` · `config` · `util` · `collect` · `featcard` · `depth` · `pool` · `render` + `__init__` / `__main__`。

**幂等/契约测试**（`tests/test_core.py`，**不得删，只能加**）：

| 测试 | 阶段 |
|---|---|
| `test_report_is_byte_identical` · `test_as_of_dominates` · `test_stable_json_is_sorted` | ✅ L0 |
| `test_no_llm_involved` · `test_no_credentials_falls_back_to_off` | ✅ L0 |
| `test_quota_downgrade_is_recorded` · `test_budget_gate_cannot_be_overridden` · `test_manual_override_bypasses_quota_but_not_budget` | ✅ L0 |
| `test_template_page_is_a_miss` · `test_real_content_is_a_hit` | ⬜ L1（建 `probe_external` 时补） |
| `test_three_class_output` · `test_not_applicable_when_domain_mismatch` | ⬜ L3（建 `patterns.py` 时补） |

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
| 数据布局 | 设计方案 §8 |
| 成本观测 | 设计方案 §9 |
| 报告结构 | 执行手册 附录 A |
| 验收模板 | 执行手册 §6 |

---

## 7. 每阶段收尾必做

- [ ] 门禁全绿：`pytest` / `ruff` / `ruff format` / **mypy strict**
- [ ] 追加 `docs/开发日志.md` 本阶段章节（实测、决策依据、坑）
- [ ] 更新本文件（若内容有变）
- [ ] 提交前列 `git status` 确认；核对 `git ls-files | grep -E '\.env$|secrets|\.db$'` 为空
- [ ] **提交 + 打 tag**（如 `l0`），再通知项目负责人刷新文档
- [ ] 输出验收报告（八段，在会话输出**不落成文件**），**停下**

**验收报告八段**：`已完成 / DoD 核对 / 关键文件清单 / 测试与覆盖率 / 真实运行证据 / 遇到的坑与解决 / 待决策问题（≤1）/ 下一步`

★ **真实运行证据必须非空**（单测通过 ≠ 功能真的产出过内容）；
★ **诚实暴露局限**比漂亮的完成度有价值。

---

## 8. 数据布局（真源 vs 可丢弃）

```
config.yaml                      # 唯一配置真源
patterns/*.yaml                  # 规律库（真源，可 diff）
data/
├── ledger/selected.jsonl        # ★ append-only：何时选过、为什么选
├── pool/pool.jsonl              # 候选池（append-only + 观测序列）
├── snapshots/<repo>/<name>-<date>.md   # 外部资料快照 + sha256
├── featcards/<owner>__<repo>__<commit>.json
└── costs/costs.jsonl            # append-only：调用/降级/预算事件
reports/<owner>__<repo>__<date>.md
site/                            # L4 静态站（可丢弃、可重建）
```

**真源**：`patterns/` · `data/ledger` · `data/pool` · `data/snapshots` · `data/costs` · `reports/`
**可丢弃可重建**：`data/featcards/` · `site/` · 任何 DB 索引

---

## 9. 里程碑

| 阶段 | 目标 | 完成判据 |
|---|---|---|
| **L0** | 采集 + 建池 + 去重 + **off 档体检报告** | 对 1 个真实仓库跑出完整体检报告（**零 LLM**） |
| **L1** | 特征卡 L0 + 依赖图 + 外部工具（fail-closed）+ fast 档 | 特征卡含证据；Mermaid 可渲染 |
| **L2** | 档位四层 + 预算闸门 + 成本观测 + 定时 | `cost` 可用；配额用完自动降级并留痕 |
| **L3** | 模式召回 + 批量抽象 + 反例自动挖掘 | 积累 ≥5 个项目后触发首次抽象 |
| **L4** | 静态站点（只读） | 由 MD + JSON 生成，无后端 |

---

## 10. 你还要维护的文档

| 文档 | 建的时刻 |
|---|---|
| `README.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | L0 首个 tag |
| `docs/开发日志.md` | L0 验收后（按时间记事实、实测、坑） |
| `docs/数据源手册.md` | L0 验收后（**归并已有实测文件，不新造**） |
| `docs/成本预算.md` | **L1 首次真实调用后**（L0 期间无真实花费，不建） |
| `docs/经验固化.md`（工程侧） | 攒够第一条工程教训 |
| `docs/功能总览.md` | 收尾 |

★ **不预建空文档**。★ **数据源手册用已有实测材料归并**：
`外部工具命中率实测_推理Infra组.md` / `_Agent训练组.md` / `watchlist星标活跃度复核.md` / `_meas/token_result.json`

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
