"""采集：可选源降级、必需源失败、树截断、翻页链接解析。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from osslens.collect import fetch_snapshot, parse_slug
from osslens.util import FixedClock, HttpClient, HttpError, OsslensError, UsageError, _next_link

BASE = "https://api.example.test"
AS_OF = datetime(2026, 11, 2, tzinfo=UTC)


def _client(handler: Callable[[httpx.Request], httpx.Response], *, retries: int = 0) -> HttpClient:
    return HttpClient(
        BASE,
        max_retries=retries,
        backoff_seconds=0,
        sleep=lambda _seconds: None,
        transport=httpx.MockTransport(handler),
    )


def _ok_payloads(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/repos/o/r":
        return httpx.Response(
            200, json={"full_name": "o/r", "stargazers_count": 10, "default_branch": "main"}
        )
    if path.endswith("/languages"):
        return httpx.Response(200, json={"Python": 100})
    if path.endswith("/contributors"):
        return httpx.Response(200, json=[{"login": "a", "contributions": 5, "type": "User"}])
    if path.endswith("/releases"):
        return httpx.Response(200, json=[])
    if path.endswith("/commits"):
        return httpx.Response(
            200, json=[{"sha": "s1", "commit": {"author": {"date": "2026-10-01T00:00:00Z"}}}]
        )
    if "/git/trees/" in path:
        return httpx.Response(
            200, json={"truncated": False, "tree": [{"path": "a.py", "type": "blob", "size": 10}]}
        )
    return httpx.Response(404, json={"message": "not found"})


def test_optional_source_failure_is_degraded_not_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contributors"):
            return httpx.Response(500, text="boom")
        return _ok_payloads(request)

    client = _client(handler)
    try:
        snapshot = fetch_snapshot(client, "o", "r", as_of=AS_OF, clock=FixedClock(AS_OF))
    finally:
        client.close()
    assert snapshot.degraded is True
    assert snapshot.degraded_sources == ("contributors",)
    assert snapshot.data["contributors"] == []
    assert snapshot.data["repo"]["stars"] == 10


def test_missing_repo_metadata_is_fatal() -> None:
    client = _client(lambda request: httpx.Response(404, text="not found"))
    try:
        with pytest.raises(OsslensError):
            fetch_snapshot(client, "o", "r", as_of=AS_OF, clock=FixedClock(AS_OF))
    finally:
        client.close()


def test_truncated_tree_is_flagged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"truncated": True, "tree": []})
        return _ok_payloads(request)

    client = _client(handler)
    try:
        snapshot = fetch_snapshot(client, "o", "r", as_of=AS_OF, clock=FixedClock(AS_OF))
    finally:
        client.close()
    statuses = {(note.source, note.status) for note in snapshot.notes}
    assert ("tree", "truncated") in statuses
    assert ("used_by", "unavailable") in statuses


def test_http_error_after_retries() -> None:
    client = _client(lambda request: httpx.Response(500, text="boom"), retries=2)
    try:
        with pytest.raises(HttpError) as info:
            client.get_json("/repos/o/r")
    finally:
        client.close()
    assert info.value.status == 500
    assert len(client.requests_made) == 3


def test_pagination_follows_next_link() -> None:
    pages = {
        "1": httpx.Response(
            200,
            json=[{"login": "a"}],
            headers={"Link": '<https://api.github.com/x?page=2>; rel="next"'},
        ),
        "2": httpx.Response(200, json=[{"login": "b"}]),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        return pages[page]

    client = _client(handler)
    try:
        items = client.get_pages("/x")
    finally:
        client.close()
    assert [item["login"] for item in items] == ["a", "b"]


def test_next_link_parser() -> None:
    header = '<https://api.github.com/x?page=2>; rel="next", <https://api.github.com/x?page=5>; rel="last"'
    assert _next_link(header) == "https://api.github.com/x?page=2"
    assert _next_link("") is None


def test_parse_slug_validation() -> None:
    assert parse_slug("owner/repo") == ("owner", "repo")
    with pytest.raises(UsageError):
        parse_slug("owner")
    with pytest.raises(UsageError):
        parse_slug("owner/repo/extra")
