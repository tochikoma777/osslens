"""确定性工具：异常 / HTTP / sha256 / 排序 / 原子写 / JSONL / r4。

幂等三条铁律在本模块落地：
1. 时间由调用方注入（`Clock`），本模块不产生"当前时间"。
2. 集合输出前必须经 `sorted`（路径升序 / 计数降序 + 路径升序 tie-break）。
3. 浮点一律 `r4`，JSON 一律 `stable_json`（sort_keys/ensure_ascii=False/indent=2）。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import parse_qsl, urlsplit

import httpx

ISO_SECONDS = "%Y-%m-%dT%H:%M:%SZ"


# --------------------------------------------------------------------------- 异常


class OsslensError(Exception):
    """本项目的基类异常。"""


class ConfigError(OsslensError):
    """配置错误 → 退出码 1。"""


class UsageError(OsslensError):
    """参数错误 → 退出码 2。"""


class HttpError(OsslensError):
    """HTTP 层失败（含重试耗尽）。"""

    def __init__(self, url: str, status: int, reason: str) -> None:
        super().__init__(f"HTTP {status} {url}: {reason}")
        self.url = url
        self.status = status
        self.reason = reason


# --------------------------------------------------------------------------- 时间


class Clock(Protocol):
    """时间来源。测试用受控时钟替换，生产用 SystemClock。"""

    def now(self) -> datetime: ...


class SystemClock:
    """真实时钟——**只允许**在非报告路径（如 `pool add` 记录观测时刻）使用。"""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """受控时钟：跨天 / 跨周时序测试专用。"""

    def __init__(self, instant: datetime) -> None:
        self._instant = ensure_utc(instant)

    def now(self) -> datetime:
        return self._instant

    def advance(self, *, days: float = 0, hours: float = 0) -> None:
        self._instant = self._instant + timedelta(days=days, hours=hours)


def ensure_utc(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        return instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC)


def parse_iso(text: str) -> datetime:
    """解析 ISO8601（允许 `Z` 结尾）。无法解析 → ValueError。"""
    cleaned = text.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(cleaned))


def fmt_iso(instant: datetime) -> str:
    return ensure_utc(instant).strftime(ISO_SECONDS)


def fmt_date(instant: datetime) -> str:
    return ensure_utc(instant).strftime("%Y-%m-%d")


def start_of_day(instant: datetime) -> datetime:
    utc = ensure_utc(instant)
    return utc.replace(hour=0, minute=0, second=0, microsecond=0)


def start_of_week(instant: datetime) -> datetime:
    """周一 00:00Z 为周起点（与 §11 周配额口径一致）。"""
    day = start_of_day(instant)
    return day - timedelta(days=day.weekday())


def start_of_month(instant: datetime) -> datetime:
    return start_of_day(instant).replace(day=1)


def days_between(later: datetime, earlier: datetime) -> int:
    return (start_of_day(later) - start_of_day(earlier)).days


# --------------------------------------------------------------------------- 数值与排序


def r4(value: float) -> float:
    """统一四位小数；消除 -0.0，避免同一数值产生两种字节表示。"""
    rounded = round(float(value), 4)
    if rounded == 0:
        return 0.0
    return rounded


def zscore(values: Sequence[float]) -> list[float]:
    """同通道内 z-score（总体标准差）。样本 <2 或方差为 0 → 全 0.0。

    规范来源：设计方案 §6.1——"样本 <2 时返回 0.0（不是估算）"。
    """
    count = len(values)
    if count < 2:
        return [0.0] * count
    mean = sum(values) / count
    variance = sum((value - mean) ** 2 for value in values) / count
    if variance <= 0:
        return [0.0] * count
    deviation = math.sqrt(variance)
    return [r4((value - mean) / deviation) for value in values]


def sort_paths(paths: Iterable[str]) -> list[str]:
    return sorted(paths)


def sort_count_then_path(items: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    """计数值降序 + 路径升序 tie-break（§7 坑 2）。"""
    return sorted(items, key=lambda item: (-item[1], item[0]))


# --------------------------------------------------------------------------- 哈希与 JSON


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json(obj: Any) -> str:
    """幂等 JSON：sort_keys + ensure_ascii=False + indent=2（§7 补充规约）。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)


def stable_json_line(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def atomic_write_text(path: Path, text: str) -> None:
    """临时文件 + rename，避免读到半截文件（执行手册 §2.3）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise OsslensError(f"{path}:{line_no} 不是合法 JSON：{exc}") from exc
        if not isinstance(parsed, dict):
            raise OsslensError(f"{path}:{line_no} 期望 JSON 对象，实际 {type(parsed).__name__}")
        records.append(cast(dict[str, Any], parsed))
    return records


def append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    """真源 append-only：只追加，永不覆盖（红线 #6）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(stable_json_line(dict(record)))
        stream.write("\n")


# --------------------------------------------------------------------------- 边界解析


def as_dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def as_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def safe_filename(text: str) -> str:
    """非法字符 → `-`（执行手册 §2.3）。"""
    illegal = '/\\:*?"<>|'
    cleaned = "".join("-" if char in illegal else char for char in text)
    return cleaned.strip() or "-"


# --------------------------------------------------------------------------- HTTP


class HttpClient:
    """统一 HTTP 客户端：限速 / 重试 / UA 复用（红线 #22）。

    `requests_made` 记录**实际发出的每一个 URL**，是 off 档零 LLM 的取证依据之一。
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 20.0,
        user_agent: str = "osslens/0.1",
        max_retries: int = 3,
        backoff_seconds: float = 1.5,
        accept: str = "application/vnd.github+json",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, max_retries)
        self._backoff = backoff_seconds
        self._sleep = sleep
        self._requests_made: list[str] = []
        headers = {"User-Agent": user_agent, "Accept": accept}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers=headers,
            transport=transport,
            follow_redirects=True,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def requests_made(self) -> tuple[str, ...]:
        return tuple(self._requests_made)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        response = self._get(path, params)
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise HttpError(str(response.url), response.status_code, "响应不是合法 JSON") from exc

    def get_pages(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        max_pages: int = 10,
    ) -> list[Any]:
        """按 Link rel=next 翻页，**最多 max_pages 页**，避免无界抓取。"""
        query: dict[str, Any] = {"per_page": 100}
        if params:
            query.update(params)
        target = path
        items: list[Any] = []
        for _ in range(max_pages):
            response = self._get(target, query)
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise HttpError(
                    str(response.url), response.status_code, "响应不是合法 JSON"
                ) from exc
            items.extend(as_list(payload))
            next_url = _next_link(response.headers.get("Link", ""))
            if next_url is None:
                break
            parts = urlsplit(next_url)
            target = parts.path
            query = dict(parse_qsl(parts.query))
        return items

    def _get(self, path: str, params: Mapping[str, Any] | None) -> httpx.Response:
        url = f"{self._base_url}{path}"
        last_error: HttpError | None = None
        for attempt in range(self._max_retries + 1):
            self._requests_made.append(url)
            try:
                response = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                last_error = HttpError(url, 0, f"网络错误：{exc}")
                if attempt >= self._max_retries:
                    raise last_error from exc
                self._sleep(self._backoff * (2**attempt))
                continue
            retryable = response.status_code in (403, 429) or response.status_code >= 500
            if retryable and attempt < self._max_retries:
                self._sleep(_retry_delay(response, self._backoff * (2**attempt)))
                continue
            if response.status_code >= 400:
                raise HttpError(url, response.status_code, _snippet(response))
            return response
        assert last_error is not None
        raise last_error


def _retry_delay(response: httpx.Response, fallback: float) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return min(float(header), 60.0)
        except ValueError:
            return fallback
    return fallback


def _snippet(response: httpx.Response) -> str:
    text = response.text.strip().replace("\n", " ")
    return text[:200] if text else "（空响应体）"


def _next_link(header: str) -> str | None:
    for part in header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        if 'rel="next"' not in segments[1]:
            continue
        return segments[0].strip().strip("<>")
    return None
