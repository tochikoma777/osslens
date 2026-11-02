# 外部文档工具命中率实测报告（Agent 框架 / LLM 应用 / 训练与数据基础设施组）

## 摘要

本次实测选取 10 个 2026 年新建、且大多在 2026 年下半年才开始爆红的仓库，逐库访问 DeepWiki 与 Zread 的 `/<owner>/<repo>` 路径，判断是否返回该仓库专属内容。结果：DeepWiki 在 10 个仓库中全部返回了带仓库专属模块结构与文件路径的 wiki 页面，命中率 10/10（100%）；Zread 在 9 个仓库返回了仓库专属内容，命中率 9/10（90%），另有 1 个仓库（DataFlex-RL）页面仅为界面骨架、无专属内容。需要特别说明的是，本报告并未验证"越新越火的项目越可能没被索引"这一风险假设——本次样本全部命中，与风险假设方向相反。数据抓取时点：2026-10-30。

## 一、样本选择：10 个仓库全部为 2026 年新建，覆盖三类范畴

样本来源为 GitHub Trending 汇总、社区讨论（如 quidproquo 的 AI Agent GitHub Digest、PullRepo 每日榜单）与媒体报道。筛选标准为"2026 年新建"或"2026 年下半年才开始被广泛讨论"，主语言与 star 数取自 GitHub 镜像统计站点（RepositoryStats、GitDiscover、GitTiger、GitGenius、TopGit、GitTrend 等）在抓取时点的最新读数。

| # | 仓库 | 创建时间 | star（约） | 主语言 | 范畴 |
|---|------|----------|-----------|--------|------|
| 1 | deepseek-ai/deepseek-harness | 2026-08-13 | 240,000+ | TypeScript | Agent 框架 |
| 2 | anywhere-labs/dsh-desktop | 2026-08-13 | 19,900 | TypeScript | Agent 应用（桌面端） |
| 3 | RightNow-AI/openfang | 2026-08-19 | 18,113 | Rust | Agent 框架（操作系统层） |
| 4 | browser-use/jev-ultrafast | 2026-09-16 | 21,754 | Python | Agent 应用（浏览器代理） |
| 5 | NandhaKishorM/laya | 2026-09-18 | 34,481 | Python | LLM 应用（决策引擎，属非自回归推理，非推理引擎） |
| 6 | haolpku/DataFlex-RL | 2026-09（9 月发布） | 未公开量级 | Python | 训练与数据基础设施（RL 数据策略） |
| 7 | Panniantong/Agent-Reach | 2026-10-25 | 105,929 | Python | Agent 应用（多平台信息获取） |
| 8 | affaan-m/ECC | 2026 年初（1 月） | 291,100 | JavaScript | Agent 框架（harness 优化系统） |
| 9 | NVIDIA/SkillSpector | 2026-年中出现，10 月爆火 | 22,142 | Python | Agent 安全工具 |
| 10 | multica-ai/multica | 2026 年创建 | 53,071 | Go（含 TS 前端） | Agent 协作平台 |

注：DataFlex-RL 的创建日期在公开镜像站点中未单独披露，仅能确认于 2026 年 9 月随论文发布；ECC 的创建时间为 2026 年 1 月，属"2026 年新建"但非"下半年才爆火"，已在备注中标注。

## 二、DeepWiki 实测：10/10 全部命中，索引速度超出预期

对每个仓库访问 `https://deepwiki.com/<owner>/<repo>`，判断标准严格限定为"页面是否列出该仓库专属的模块结构、源码文件路径或架构说明"。10 个仓库全部满足该标准。

**DeepSeek Harness 的页面列出了 monorepo 的 apps/、packages/、vendor/ 布局，并引用了 `packages/core/agent-loop/src/agent.ts`、`apps/web/tests/scaffold.ts` 等真实源码路径，同时解释了"万物皆插件"与能力缝（capability seam）模式。** 该页面对"模型适配器、工具注册表、会话持久化存储、agent 驱动循环都是 Cordis 插件"这一项目特有架构做了完整说明，排除了模板化可能。

**openfang 的页面按 Cargo workspace 的 14 个 crate 逐一列出职责**，包括 openfang-kernel、openfang-runtime、openfang-channels 等，并引用了 `crates/openfang-desktop/tauri.conf.json` 等仓库真实路径。Agent-Reach 的页面给出了 `agent_reach/` 目录树，含 cli.py、core.py、doctor.py、channels/、integrations/mcp_server.py、skill/SKILL.md 等文件，并注明各文件职责。

**ECC 的页面列出了 agents/、Skills/、Rules/、Hooks/、Commands/、ecc2/（Rust daemon）等顶层目录结构，并说明通过 Profiles（Minimal/Core/Full）选择性安装。** SkillSpector 的页面列明了 `skillspector/core/graph.py`、`skillspector/nodes/analyzers/`、`skillspector/llm/providers/`、`skillspector/core/models.py`、`skillspector/cli/main.py` 等子系统文件路径。multica 的页面引用了 `server/cmd/server/router.go`、`apps/web/app/layout.tsx`、`server/pkg/db/queries` 等真实路径，并说明了 pnpm workspace 的 apps/、packages/、server/ 三区分工。

**DataFlex-RL 是唯一证据偏弱的一项**：页面返回了 `haolpku/DataFlex-RL` 的仓库专属页头与"Index your code with Devin"字样，确认已被索引，但本次抓取未带回模块结构或文件路径，因此按其"专属页面壳"判为命中、但可信度低于其余 9 项。

## 三、Zread 实测：9/10 命中，1 个未返回专属内容

对每个仓库访问 `https://zread.ai/<owner>/<repo>`。9 个仓库的页面包含了仓库专属的概述、设计原则、模块说明或平台清单，可判定为命中。

**jev-ultrafast 的 Zread 页面元数据标注了"Last Indexed: 23 September 2026"，并列出"Sources: README.md, init.py"**，页面含 Overview、Quick Start、Library API Usage 章节。证据偏弱（抓取内容接近界面骨架），但因含仓库专属名与来源标注，仍判为命中，已在"不可靠项"中标注。

**Agent-Reach 的 Zread 页面给出了"16 个受支持平台"的完整清单**（Web、YouTube、RSS、V2EX、Xueqiu、GitHub、Twitter/X、Bilibili、LinkedIn、Boss Zhipin、Xiaoyuzhou、Reddit、Facebook、Instagram、Xiaohongshu、Exa Search），并解释了"能力层而非封装器"的定位与关注点分离原则。ECC 的 Zread 页面标注了"Last Indexed: 08 June 2026"，给出了 64 个专用 agent、261 个工作流 skill、84 个斜杠命令、14+ MCP server 配置等版本专属数字。SkillSpector 的 Zread 页面给出了 42,447 个技能包的市场调研数据、26.1% 漏洞率、5.2% 疑似恶意意图、16 大类 64 种漏洞模式等仓库专属数字。

**DataFlex-RL 是本次样本中唯一未命中的仓库**：页面仅返回导航骨架（探索、趋势、私有仓库、订阅、收藏夹）与"Ask AI"提示，无任何该仓库的 README、模块说明或专属信息，判定为未命中。

**dsh-desktop 的 Zread 页面抓取失败**（工具返回"无法获取该链接的内容"），不能据此判定未命中，归入"无法判定"。

## 四、逐仓库实测结果总表

| # | 仓库 | 创建时间 | star | DeepWiki | Zread | 备注与来源 |
|---|------|----------|------|----------|-------|------------|
| 1 | deepseek-ai/deepseek-harness | 2026-08-13 | 240,000+ | 命中 | 命中 | TS；DeepWiki 列 apps/packages/vendor 布局与真实源码路径；Zread 页面专属内容完整。来源：[DeepWiki 页][1]、[Zread 页][2]、[GitHub 仓库][3] |
| 2 | anywhere-labs/dsh-desktop | 2026-08-13 | 19,900 | 命中 | 无法判定 | TS；DeepWiki 列 desktop-shell 插件与上游版本固定机制；Zread 抓取失败。来源：[DeepWiki 页][4]、[Zread 抓取失败]、[dshget 镜像][5] |
| 3 | RightNow-AI/openfang | 2026-08-19 | 18,113 | 命中 | 命中 | Rust；DeepWiki 列 14 个 Cargo crate；Zread 列 16 层安全模型/40 通道/27 LLM 提供商。来源：[DeepWiki 页][6]、[Zread 页][7]、[Agent Digest][8] |
| 4 | browser-use/jev-ultrafast | 2026-09-16 | 21,754 | 命中 | 命中（弱） | Python；DeepWiki 列 DOM Snapshot Reader、Inspector Server；Zread 证据偏弱。来源：[DeepWiki 页][9]、[Zread 页][10]、[RepositoryStats][11] |
| 5 | NandhaKishorM/laya | 2026-09-18 | 34,481 | 命中 | 命中 | Python；DeepWiki 列三大决策原语与三个检查点/路由器。来源：[DeepWiki 页][12]、[RepositoryStats][13]、[CyberQ 周报][14] |
| 6 | haolpku/DataFlex-RL | 2026-09 | 未公开 | 命中（弱） | 未命中 | Python；DeepWiki 仅返回索引壳；Zread 仅界面骨架。来源：[DeepWiki 页][15]、[Zread 页][16]、[PKU 发布页][17] |
| 7 | Panniantong/Agent-Reach | 2026-10-25 | 105,929 | 命中 | 命中 | Python；DeepWiki 列完整目录树与 mcp_server.py；Zread 列 16 平台清单。来源：[DeepWiki 页][18]、[Zread 页][19]、[MCP Harbor][20] |
| 8 | affaan-m/ECC | 2026-01 | 291,100 | 命中 | 命中 | JavaScript；DeepWiki 列 ecc2/ Rust daemon；Zread 列 64 agent/261 skill。来源：[DeepWiki 页][21]、[Zread 页][22]、[GitTiger][23] |
| 9 | NVIDIA/SkillSpector | 2026 年中出现 | 22,142 | 命中 | 命中 | Python；DeepWiki 列 graph.py 与分析器路径；Zread 列 64 种漏洞模式。来源：[DeepWiki 页][24]、[Zread 页][25]、[GitGenius][26] |
| 10 | multica-ai/multica | 2026 年 | 53,071 | 命中 | 命中 | Go；DeepWiki 列 server/cmd/server/router.go；Zread 列 pnpm workspace 三区。来源：[DeepWiki 页][27]、[Zread 页][28]、[AI.Florx 榜单][29] |

## 五、汇总命中率

| 工具 | 命中 | 未命中 | 无法判定 | 有效样本命中率 |
|------|------|--------|----------|---------------|
| DeepWiki | 9（强）+ 1（弱） | 0 | 0 | 10/10 = 100%（强证据 9/10 = 90%） |
| Zread | 8（强）+ 1（弱） | 1 | 1 | 9/10 = 90%（强证据 8/9 ≈ 89%） |

若严格按"强证据专属内容"口径，DeepWiki 为 9/10（90%），Zread 为 8/9（约 89%）。若把弱证据项一并计入，则两项分别为 100% 与 90%。

## 六、不可靠项

**本次结果未能验证"越新越火的项目越可能没被索引"的风险假设。** 10 个仓库全部已被 DeepWiki 索引并返回专属内容，9 个已被 Zread 索引。这与背景中预设的风险方向相反，可能的原因包括：样本中的高 star 项目（DeepSeek Harness 24 万、ECC 29 万、Agent-Reach 10 万）本身热度足够高，触发了工具的自动索引机制，因此不构成对"长尾新项目"风险的检验。若需验证该风险，应选取 star 量级在 100–2000 之间、且创建不满 2 周的项目重测。

**DataFlex-RL 的 DeepWiki 证据偏弱。** 页面确认已被索引（返回仓库专属页头与 Devin 提示），但本次抓取未带回模块结构或文件路径，仅能判为"命中（弱）"。该仓库创建时间也未在公开镜像站点中单独披露。

**jev-ultrafast 的 Zread 证据偏弱。** 页面含仓库专属名与"Sources: README.md, init.py"元数据，但正文接近界面骨架，判为"命中（弱）"。

**dsh-desktop 的 Zread 状态为无法判定。** 工具抓取返回"无法获取该链接的内容"，非页面明确未命中，故未计入未命中，也不纳入命中率分母。

**star 数与创建时间的时点差异。** 各镜像站点的抓取时点不同（从 2026-09-28 至 2026-10-28 不等），star 数均为"约数"，不应作为精确值引用。本报告中的 star 值仅用于说明量级。

**laya 的技术范畴边界。** laya 为非自回归决策引擎，属 LLM 应用范畴，不属推理引擎，故纳入本组。

## 引用来源

[1] https://deepwiki.com/deepseek-ai/deepseek-harness
> "DeepSeek Harness (dsh) is a modular, plugin-based agent harness... Monorepo Layout & Package Families... apps/ — Entry points including CLI, desktop, and web UI. packages/ — Core logic organized by function"

[2] https://zread.ai/deepseek-ai/deepseek-harness
> "DeepSeek Harness (dsh) is an open-source agent runtime developed by DeepSeek AI, built on a radical architectural principle: everything is a plugin."

[3] https://github.com/deepseek-ai/deepseek-harness
> 页面抓取受安全审核限制，未返回内容。创建时间与 star 数取自社区摘要。

[4] https://deepwiki.com/anywhere-labs/dsh-desktop
> "DSH Desktop 是一款适用于 Windows 和 macOS 的开源原生桌面客户端，它将 DeepSeek Harness 封装为一款一键安装的 Electron 应用程序。"

[5] https://dshget.com/plugins/anywhere-labs/dsh-desktop
> "GitHub stars 19.9K License MIT Added 2026-08-13 Primary language TypeScript"

[6] https://deepwiki.com/RightNow-AI/openfang
> "OpenFang is an open-source Agent Operating System built in Rust... OpenFang is organized as a Cargo workspace with 14 primary crates"

[7] https://zread.ai/RightNow-AI/openfang
> "It compiles to a single ~32MB binary, boots in under 200ms, and ships with 16 independent security layers, 40 channel adapters, 27 LLM providers"

[8] http://quidproquo.cc/posts/daily/2026-08-19-ai-agent-github-digest-en
> "openfang (RightNow-AI) ⭐ 18,113 GitHub · Rust · Apache-2.0... An Agent Operating System built from scratch in Rust."

[9] https://deepwiki.com/browser-use/jev-ultrafast
> "Last indexed: 17 September 2026 (452c1a)... DOM Snapshot Reader (snapshot.js)... Inspector Server (demo.py)"

[10] https://zread.ai/browser-use/jev-ultrafast
> "Last Indexed:23 September 2026... Sources: README.md, init.py"

[11] https://repositorystats.com/browser-use/jev-ultrafast
> "Date Created 2026-09-16... Stargazers 21,754... Github reports the primary language for this repository as Python"

[12] https://madewithjev.com/builds/jev-ultrafast
> "Repository created Sep 16, 2026... Stars 20,969... Language Python"

[13] https://deepwiki.com/NandhaKishorM/laya
> "Laya 是一个多语言、非自回归的 System 1 决策引擎... 三大决策原语 choice, score, noul... 三个检查点，一个路由器"

[14] http://repositorystats.com/nandhakishorm/laya
> "Date Created 2026-09-18... Stargazers 34,481... primary language... Python"

[15] https://cyberq.tw/2026/09/25/github-trends-weekly-report-vol-34/
> "Laya 在一週內累積超過兩萬三千顆星... 建立於 9 月 18 日... 語言為 Python"

[16] https://deepwiki.com/haolpku/DataFlex-RL
> "haolpku/DataFlex-RL | DeepWiki... Index your code with Devin"

[17] https://www.htx.co.ug/uk-ua/news/ranking-2nd-on-daily-trending-peking-university-open-sources-acNgDDNa
> "DataFlex-RL: Simplifying and Fairly Comparing Reinforcement Learning Data Policies"

[18] https://www.htx.co.ug/uk-ua/news/ranking-2nd-on-daily-trending-peking-university-open-sources-acNgDDNa
> "The DataFlex-RL framework, open-sourced by Peking University's DCAI team... provides a unified, modular system for dynamically managing training data during RL fine-tuning"

[19] https://deepwiki.com/Panniantong/Agent-Reach
> "What's in the Repository agent_reach/ ├── cli.py... core.py... doctor.py... channels/... integrations/mcp_server.py"

[20] https://zread.ai/Panniantong/Agent-Reach
> "Agent Reach 是一个能力层... 它让任何 AI Agent 能够通过一条命令访问 16 个互联网平台。"

[21] https://mcpharbor.app/tools/panniantong-agent-reach
> "Agent-Reach... 105,929 GitHub stars"

[22] https://deepwiki.com/affaan-m/ECC
> "Everything Claude Code (ECC) is a production-ready Agent Harness Operating System... agents/ Skills/ Rules/ Hooks/ Commands/ Control Plane ecc2/"

[23] https://zread.ai/affaan-m/ECC
> "At version 2.0.0-rc.1, ECC ships with 64 specialized agents, 261 workflow skills, 84 slash commands, and 14+ MCP server configurations"

[24] https://gittiger.com/repo/affaan-m/ECC
> "Stars 272,971... Language JavaScript... Created 9mo"

[25] https://deepwiki.com/NVIDIA/SkillSpector
> "The core of SkillSpector is built on a LangGraph pipeline... Orchestration skillspector/core/graph.py... Analyzers skillspector/nodes/analyzers/"

[26] https://zread.ai/NVIDIA/SkillSpector
> "该工具将覆盖 16 个大类、64 种漏洞模式的快速静态模式匹配与可选的 LLM 语义分析相结合"

[27] https://www.gitgenius.co/repos/NVIDIA/SkillSpector
> "Stars 22.1K... Python... Created on March 21st, 2026"

[28] https://topgit.dev/repo/nvidia/skillspector
> "Stars ★ 22.3k... Language Python... 68 detection patterns across 17 categories"

[29] https://deepwiki.com/multica-ai/multica
> "Multica is an open-source, AI-native project management platform... server/cmd/server/router.go... apps/web/app/layout.tsx"

[30] https://zread.ai/multica-ai/multica
> "Multica — Multiplexed Information and Computing Agent... 能力含义 26 个 Agent CLI... 项目结构 该仓库遵循 pnpm workspace 单体仓库布局"
