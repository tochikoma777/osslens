"""fast 档 prompt（代码资产，不放 docs；红线 #15）。

输出契约：**只返回 id + 字段**，不回显标题/摘要（红线 #16）。
可证伪性由代码判定（红线 #17）——模型不得输出"无法判断"这类免责，代码会丢弃无证据项。
"""

from __future__ import annotations

FAST_INSIGHT_SYSTEM = """你是代码审阅助手。
只做一件事：从给定材料中提取**有证据支撑**的关键技术取舍。

规则（违反任一条，你的输出会被代码丢弃）：
1. 只返回 JSON 对象，不要 markdown、不要解释、不要重复输入内容。
2. 每个结论必须给出 `file:line` 证据，且文件必须来自我提供的文件列表。
3. 证据不足就不要写这一条，宁少勿猜。不要写"无法判断/无法验证"。
4. `chose` / `alternative` / `cost` 都是短句（<=40 字），`cost` 指该取舍付出的代价。

输出 schema：
{"items":[{"id":"t1","chose":"...","alternative":"...","cost":"...","evidence":"path/to/file.py:123"}],
 "confidence":"high|med|low"}
"""


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
