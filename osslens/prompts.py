"""分档 prompt（代码资产，不放 docs；红线 #15）。

输出契约：**只返回 id + 字段**，不回显标题/摘要（红线 #16）。
可证伪性由代码判定（红线 #17）——模型不得输出"无法判断"这类免责，代码会丢弃无证据项。
fast / strong 共用同一输出 schema（parse_insight 判废口径不变），差异只在推理深度与 system 文本；
system 文本进入 cache_key，两档结果缓存天然隔离；schema 变更（新增 paradigm_tags）
也会使缓存键同步失效。
"""

from __future__ import annotations

from .llm import PARADIGM_TAGS

# 受控词表约束：模型只能从此表选 paradigm_tags，表外值由 normalize_paradigm_tags 丢弃。
_TAG_HINT = "paradigm_tags 受控词表（只能选 0–3 个，表外值由代码丢弃）：" + " / ".join(
    sorted(PARADIGM_TAGS)
)
_SCHEMA_LINE = (
    '{"items":[{"id":"t1","chose":"...","alternative":"...","cost":"...","evidence":"path/to/file.py:123"}],\n'
    ' "confidence":"high|med|low",\n'
    ' "paradigm_tags":["缓存复用","深优化"]}'
)

FAST_INSIGHT_SYSTEM = (
    "你是代码审阅助手。\n"
    "只做一件事：从给定材料中提取**有证据支撑**的关键技术取舍。\n\n"
    "规则（违反任一条，你的输出会被代码丢弃）：\n"
    "1. 只返回 JSON 对象，不要 markdown、不要解释、不要重复输入内容。\n"
    "2. 每个结论必须给出 `file:line` 证据，且文件必须来自我提供的文件列表。\n"
    '3. 证据不足就不要写这一条，宁少勿猜。不要写"无法判断/无法验证"。\n'
    "4. `chose` / `alternative` / `cost` 都是短句（<=40 字），`cost` 指该取舍付出的代价。\n"
    "5. `paradigm_tags` 是**报告级**架构范式标签，从受控词表选 0–3 个；\n"
    "   不确定就留空数组，绝不编造。\n\n"
    "输出 schema：\n" + _SCHEMA_LINE + "\n" + _TAG_HINT + "\n"
)

STRONG_INSIGHT_SYSTEM = (
    "你是资深代码架构审阅助手，开启深度推理。\n"
    "目标：从给定材料中提炼**更少但更关键**的架构范式与设计取舍，每条都必须有可核验的代码证据。\n\n"
    "规则（违反任一条，你的输出会被代码丢弃）：\n"
    "1. 只返回 JSON 对象，不要 markdown、不要解释、不要重复输入内容。\n"
    "2. 每个结论必须给出 `file:line` 证据，且文件必须来自我提供的文件列表。\n"
    "3. 只写跨模块、跨层级的取舍；局部实现细节不要写。\n"
    '   证据不足就宁少勿猜，不要写"无法判断/无法验证"。\n'
    "4. `chose` / `alternative` / `cost` 都是短句（<=40 字），`cost` 指该取舍付出的代价。\n"
    "5. `paradigm_tags` 是**报告级**架构范式标签，从受控词表选 0–3 个；\n"
    "   不确定就留空数组，绝不编造。\n\n"
    "输出 schema：\n" + _SCHEMA_LINE + "\n" + _TAG_HINT + "\n"
)


def fast_insight_user(
    *, repo: str, commit: str, featcard_json: str, file_list: str, files_block: str
) -> str:
    return f"""仓库：{repo}
commit：{commit}

## 特征卡（确定性提取，含证据）
{featcard_json}

## 可用文件（evidence 只能引用这些路径）
{file_list}

## 源码片段
{files_block}
"""
