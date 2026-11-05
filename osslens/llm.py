"""LLM 客户端（httpx 直连 `/chat/completions`，不引入 openai SDK；红线 #21）。

三条硬约束：
- **裁剪发生在调用之前**（红线 #14）：`assemble_context` 先裁剪，再发请求。
- **结构化输出阶梯**按 (model, format) 记忆；DeepSeek 不支持 `json_schema` 时**首次即跳过第一级**。
- **结果持久化**：同一输入 hash 直接复用，既省钱又保证 `--as-of` 重跑字节一致。
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import Layout, LlmCredentials
from .util import as_dict, as_int, as_list, as_str, atomic_write_text, sha256_text, stable_json

JSON_SCHEMA = "json_schema"
JSON_OBJECT = "json_object"
PLAIN = "plain"

MAX_OUTPUT_TOKENS = 4096
CHARS_PER_TOKEN = 4
# 上下文切片上限：fast 档只做「取舍识别」，不需要整仓；超出部分不进 prompt
MAX_CONTEXT_FILES = 6
MAX_CONTEXT_FILE_CHARS = 6000


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    total_tokens: int
    # T1：strong 档 thinking 开启时，API 回显
    # completion_tokens_details.reasoning_tokens。它已含在 completion_tokens 内、
    # 按输出单价计费（不重复计费）；单列只为可核验留痕。
    reasoning_tokens: int = 0

    @classmethod
    def from_payload(cls, value: Any) -> Usage:
        payload = as_dict(value)
        hit = as_int(payload.get("prompt_cache_hit_tokens"))
        miss = as_int(payload.get("prompt_cache_miss_tokens"))
        prompt = as_int(payload.get("prompt_tokens"))
        if not hit and not miss:
            miss = prompt
        return Usage(
            prompt_tokens=prompt,
            completion_tokens=as_int(payload.get("completion_tokens")),
            cache_hit_tokens=hit,
            cache_miss_tokens=miss,
            total_tokens=as_int(payload.get("total_tokens")),
            reasoning_tokens=as_int(
                as_dict(payload.get("completion_tokens_details")).get("reasoning_tokens")
            ),
        )

    def to_json(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_hit_tokens": self.cache_hit_tokens,
            "cache_miss_tokens": self.cache_miss_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }

    @classmethod
    def from_json(cls, value: Any) -> Usage:
        payload = as_dict(value)
        return cls(
            prompt_tokens=as_int(payload.get("prompt_tokens")),
            completion_tokens=as_int(payload.get("completion_tokens")),
            cache_hit_tokens=as_int(payload.get("cache_hit_tokens")),
            cache_miss_tokens=as_int(payload.get("cache_miss_tokens")),
            total_tokens=as_int(payload.get("total_tokens")),
            reasoning_tokens=as_int(payload.get("reasoning_tokens")),
        )


@dataclass(frozen=True)
class InsightItem:
    id: str
    chose: str
    alternative: str
    cost: str
    evidence: str

    def to_json(self) -> dict[str, str]:
        return {
            "id": self.id,
            "chose": self.chose,
            "alternative": self.alternative,
            "cost": self.cost,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class Insight:
    items: tuple[InsightItem, ...]
    confidence: str
    dropped: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "items": [item.to_json() for item in self.items],
            "confidence": self.confidence,
            "dropped": list(self.dropped),
        }

    @classmethod
    def from_json(cls, value: Any) -> Insight:
        payload = as_dict(value)
        return cls(
            items=tuple(
                InsightItem(
                    id=as_str(item.get("id")),
                    chose=as_str(item.get("chose")),
                    alternative=as_str(item.get("alternative")),
                    cost=as_str(item.get("cost")),
                    evidence=as_str(item.get("evidence")),
                )
                for item in as_list(payload.get("items"))
                if isinstance(item, dict)
            ),
            confidence=as_str(payload.get("confidence"), "low"),
            dropped=tuple(as_str(item) for item in as_list(payload.get("dropped"))),
        )


@dataclass(frozen=True)
class LlmOutcome:
    status: str  # ok | cache_hit | rejected | error
    reason: str
    insight: Insight | None
    usage: Usage
    model: str
    format_used: str
    calls: int

    @property
    def spent_tokens(self) -> int:
        return 0 if self.status == "cache_hit" else self.usage.total_tokens


class LlmClient:
    def __init__(
        self,
        credentials: LlmCredentials,
        *,
        model: str,
        thinking: bool,
        timeout_seconds: float,
        max_retries: int,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = credentials.base_url.rstrip("/")
        self._api_key = credentials.api_key
        self._model = model
        self._thinking = thinking
        self._retries = max(0, max_retries)
        self._sleep = sleep
        self._timeout = timeout_seconds
        self._transport = transport
        self._formats_disabled: set[str] = set()

    def formats(self) -> tuple[str, ...]:
        ladder = [JSON_SCHEMA, JSON_OBJECT, PLAIN]
        if self._model.startswith("deepseek"):
            ladder = [JSON_OBJECT, PLAIN]
        return tuple(item for item in ladder if item not in self._formats_disabled)

    def chat_json(
        self, system: str, user: str, *, max_tokens: int = MAX_OUTPUT_TOKENS
    ) -> LlmOutcome:
        last_error = "未发起请求"
        calls = 0
        for fmt in self.formats():
            body = self._body(system, user, fmt=fmt, max_tokens=max_tokens)
            outcome = self._post(body, fmt=fmt, max_tokens=max_tokens)
            calls += outcome[0]
            if outcome[1] is not None:
                return LlmOutcome(
                    status="ok",
                    reason="",
                    insight=outcome[1],
                    usage=outcome[2],
                    model=self._model,
                    format_used=fmt,
                    calls=calls,
                )
            last_error = outcome[3]
            if "response_format" in last_error.lower() or "json_schema" in last_error.lower():
                self._formats_disabled.add(fmt)
                continue
            break
        return LlmOutcome(
            status="error",
            reason=last_error,
            insight=None,
            usage=Usage(0, 0, 0, 0, 0),
            model=self._model,
            format_used="",
            calls=calls,
        )

    def _body(self, system: str, user: str, *, fmt: str, max_tokens: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if fmt == JSON_OBJECT:
            payload["response_format"] = {"type": "json_object"}
        if not self._thinking:
            payload["thinking"] = {"type": "disabled"}
        return payload

    def _post(
        self, body: dict[str, Any], *, fmt: str, max_tokens: int
    ) -> tuple[int, Insight | None, Usage, str]:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        calls = 0
        last = "未知错误"
        for attempt in range(self._retries + 1):
            calls += 1
            try:
                with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                    response = client.post(url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                last = f"网络错误：{type(exc).__name__}"
                if attempt >= self._retries:
                    return calls, None, Usage(0, 0, 0, 0, 0), last
                self._sleep(1.5 * (2**attempt))
                continue
            if response.status_code in (401, 402):
                return (
                    calls,
                    None,
                    Usage(0, 0, 0, 0, 0),
                    f"HTTP {response.status_code}：{response.text[:120]}",
                )
            if response.status_code == 429 or response.status_code >= 500:
                last = f"HTTP {response.status_code}"
                if attempt >= self._retries:
                    return calls, None, Usage(0, 0, 0, 0, 0), last
                self._sleep(1.5 * (2**attempt))
                continue
            if response.status_code >= 400:
                return (
                    calls,
                    None,
                    Usage(0, 0, 0, 0, 0),
                    f"HTTP {response.status_code}：{response.text[:200]}",
                )

            payload = as_dict(response.json())
            usage = Usage.from_payload(payload.get("usage"))
            choices = as_list(payload.get("choices"))
            content = ""
            if choices:
                content = as_str(as_dict(as_dict(choices[0]).get("message")).get("content"))
            insight = parse_insight(content, max_tokens=max_tokens, usage=usage)
            if insight is None:
                return calls, None, usage, "判废：空输出或输出顶格"
            return calls, insight, usage, ""
        return calls, None, Usage(0, 0, 0, 0, 0), last


def parse_insight(content: str, *, max_tokens: int, usage: Usage) -> Insight | None:
    """判废规则：空输出或 `completion_tokens` 顶格 → 判废（执行手册 §2.2）。"""
    if not content.strip():
        return None
    if usage.completion_tokens >= max_tokens:
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    items = []
    for raw in as_list(as_dict(payload).get("items")):
        item = as_dict(raw)
        items.append(
            InsightItem(
                id=as_str(item.get("id")),
                chose=as_str(item.get("chose")),
                alternative=as_str(item.get("alternative")),
                cost=as_str(item.get("cost")),
                evidence=as_str(item.get("evidence")),
            )
        )
    if not items:
        return None
    return Insight(
        items=tuple(items),
        confidence=as_str(as_dict(payload).get("confidence"), "low"),
        dropped=(),
    )


def validate_insight(insight: Insight, *, allowed_paths: set[str]) -> Insight:
    """可证伪性由**代码**判定：证据路径必须在提供的文件列表里，行号必须为正。"""
    kept: list[InsightItem] = []
    dropped: list[str] = []
    for item in insight.items:
        path, _, line = item.evidence.rpartition(":")
        if not path or not line.isdigit() or int(line) <= 0:
            dropped.append(f"{item.id}: 证据格式非法 {item.evidence!r}")
            continue
        if path not in allowed_paths:
            dropped.append(f"{item.id}: 证据文件不在提供的列表内 {path!r}")
            continue
        if not (item.chose and item.alternative and item.cost):
            dropped.append(f"{item.id}: 字段不完整")
            continue
        kept.append(item)
    return Insight(items=tuple(kept), confidence=insight.confidence, dropped=tuple(dropped))


def cache_path(layout: Layout, key: str) -> Path:
    return layout.data_dir / "llm_cache" / f"{key}.json"


def cache_key(model: str, thinking: bool, system: str, user: str) -> str:
    return sha256_text(f"{model}|{thinking}|{system}|{user}")


def load_cached(cache_file: Path) -> LlmOutcome | None:
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    insight = Insight.from_json(payload.get("insight"))
    usage = Usage.from_json(payload.get("usage"))
    return LlmOutcome(
        status="cache_hit",
        reason="同一输入已有结果（结果持久化）",
        insight=insight,
        usage=usage,
        model=as_str(payload.get("model")),
        format_used=as_str(payload.get("format_used")),
        calls=0,
    )


def store_cache(cache_file: Path, outcome: LlmOutcome) -> None:
    atomic_write_text(
        cache_file,
        stable_json(
            {
                "insight": outcome.insight.to_json() if outcome.insight else None,
                "usage": outcome.usage.to_json(),
                "model": outcome.model,
                "format_used": outcome.format_used,
            }
        )
        + "\n",
    )


@dataclass(frozen=True)
class ContextBlock:
    name: str
    priority: int
    tokens: int
    text: str

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "priority": self.priority, "tokens": self.tokens}


@dataclass(frozen=True)
class Context:
    blocks: tuple[ContextBlock, ...]
    dropped: tuple[str, ...]

    @property
    def tokens(self) -> int:
        return sum(block.tokens for block in self.blocks)

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def assemble_context(
    *,
    card_json: str,
    readme: str,
    source_files: Sequence[tuple[str, str]],
    budget_tokens: int,
) -> Context:
    """裁剪发生在调用之前（红线 #14）：按信息密度从低到高丢弃。"""
    blocks: list[ContextBlock] = [
        ContextBlock("featcard", 1, estimate_tokens(card_json), f"## 特征卡\n{card_json}")
    ]
    if readme:
        blocks.append(ContextBlock("readme", 2, estimate_tokens(readme), f"## README\n{readme}"))

    chunks = []
    for path, text in source_files:
        body = f"### {path}\n```\n{text}\n```"
        chunks.append(ContextBlock(f"source_files:{path}", 4, estimate_tokens(body), body))
    blocks.extend(chunks)

    dropped: list[str] = []
    while blocks and sum(block.tokens for block in blocks) > budget_tokens:
        # 先弃优先级最低的，同级里弃最靠后的（source_files 已按引用度排序）
        victim = max(enumerate(blocks), key=lambda pair: (pair[1].priority, pair[0]))[1]
        if victim.priority <= 2 and len([b for b in blocks if b.priority <= 2]) == 1:
            break
        blocks = [block for block in blocks if block is not victim]
        dropped.append(f"{victim.name}:{victim.tokens}tok")
    return Context(blocks=tuple(blocks), dropped=tuple(dropped))
