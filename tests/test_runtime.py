from __future__ import annotations

import asyncio
import time
from urllib.parse import quote

import httpx
import pytest

import websearch
from tests.conftest import HttpMock
from websearch import _BASE_HEADERS, Tools, _build_headers, _pick_user_agent, _RateLimiter


def _make_tool(http_mock: HttpMock, **valve_overrides: object) -> Tools:
    tool = Tools()
    tool._client_factory = http_mock.factory
    for key, value in valve_overrides.items():
        setattr(tool.valves, key, value)
    return tool


def _ddg_result_html(title: str, href: str, snippet: str) -> str:
    return (
        f'<div class="result results_links">'
        f'  <h2><a class="result__a" href="{href}">{title}</a></h2>'
        f'  <a class="result__snippet">{snippet}</a>'
        f"</div>"
    )


def _wrap(target: str) -> str:
    return f"//duckduckgo.com/l/?uddg={quote(target, safe='')}"


@pytest.mark.parametrize(
    ("safe_search", "expected_kp"),
    [("strict", "1"), ("moderate", "-1"), ("off", "-2")],
)
async def test_safe_search_param_mapping(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter, safe_search: str, expected_kp: str
) -> None:
    http_mock.register_ddg(html="")
    tool = _make_tool(http_mock, safe_search=safe_search)
    await tool.web_search("query", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    assert http_mock.requests_seen[0].url.params["kp"] == expected_kp


async def test_web_search_passes_query_through(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    http_mock.register_ddg(html="")
    tool = _make_tool(http_mock)
    await tool.web_search("hello world", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    assert http_mock.requests_seen[0].url.params["q"] == "hello world"


async def test_web_search_sends_realistic_headers(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    http_mock.register_ddg(html="")
    tool = _make_tool(http_mock)
    await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    headers = http_mock.requests_seen[0].headers
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://duckduckgo.com/"
    assert headers["Accept-Language"].startswith("en-US")
    assert headers["Sec-Fetch-Mode"] == "navigate"


async def test_web_search_handles_anomaly_block(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter, emitted: list
) -> None:
    http_mock.register_ddg(html="<html>We detected an anomaly in your search query.</html>")
    tool = _make_tool(http_mock)
    raw = await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)

    import json

    payload = json.loads(raw)
    assert payload["results"] == []
    assert "rate-limited" in payload["hint"].lower()
    assert any(ev["type"] == "status" and ev["data"]["status"] == "warning" for ev in emitted)


async def test_web_search_handles_http_error_status(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    http_mock.register_ddg(html="error", status=500)
    tool = _make_tool(http_mock)
    raw = await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)

    import json

    payload = json.loads(raw)
    assert payload["results"] == []


async def test_fetch_url_strips_html(http_mock: HttpMock, fake_request: object, fake_user: dict, emitter) -> None:
    http_mock.register_fetch(
        "https://example.com/page",
        body="<html><body><script>x</script><p>Hi <b>there</b></p></body></html>",
    )
    tool = _make_tool(http_mock)
    raw = await tool.fetch_url(
        "https://example.com/page",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )

    import json

    payload = json.loads(raw)
    assert "Hi there" in payload["content"]
    assert "<script>" not in payload["content"]


async def test_fetch_url_truncates_long_body(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    long_text = "x" * 50_000
    http_mock.register_fetch(
        "https://example.com/long",
        body=f"<p>{long_text}</p>",
    )
    tool = _make_tool(http_mock)
    raw = await tool.fetch_url(
        "https://example.com/long",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )

    import json

    payload = json.loads(raw)
    assert payload["content"].endswith("... [truncated]")
    assert len(payload["content"]) <= 20_000 + len("... [truncated]")


async def test_fetch_url_handles_non_text_content_type(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter, emitted: list
) -> None:
    http_mock.register_fetch(
        "https://example.com/img",
        body="binary",
        content_type="image/jpeg",
    )
    tool = _make_tool(http_mock)
    raw = await tool.fetch_url(
        "https://example.com/img",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )

    import json

    payload = json.loads(raw)
    assert payload["content"] == ""
    assert any(ev["type"] == "status" and "Non-text" in ev["data"]["description"] for ev in emitted)


async def test_fetch_url_keeps_plain_text_content_type(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    http_mock.register_fetch(
        "https://example.com/raw.txt",
        body="line one\nline two",
        content_type="text/plain; charset=utf-8",
    )
    tool = _make_tool(http_mock)
    raw = await tool.fetch_url(
        "https://example.com/raw.txt",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )

    import json

    payload = json.loads(raw)
    assert payload["content"] == "line one\nline two"


async def test_fetch_url_emits_citation(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter, emitted: list
) -> None:
    http_mock.register_fetch("https://example.com/page", body="<p>Hello</p>")
    tool = _make_tool(http_mock)
    await tool.fetch_url(
        "https://example.com/page",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )
    citations = [ev for ev in emitted if ev["type"] == "citation"]
    assert len(citations) == 1
    assert citations[0]["data"]["source"]["url"] == "https://example.com/page"


async def test_rate_limiter_enforces_min_interval() -> None:
    limiter = _RateLimiter(min_interval_ms=120)
    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.10


async def test_rate_limiter_update_interval() -> None:
    limiter = _RateLimiter(min_interval_ms=500)
    await limiter.acquire()
    limiter.update_interval(0)
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1


def test_user_agent_rotates_across_calls() -> None:
    seen: set[str] = set()
    for _ in range(300):
        seen.add(_pick_user_agent())
    assert len(seen) >= 10


def test_build_headers_includes_base_and_user_agent() -> None:
    headers = _build_headers()
    for key in _BASE_HEADERS:
        assert headers[key] == _BASE_HEADERS[key]
    assert "User-Agent" in headers
    assert headers["User-Agent"] in websearch._USER_AGENTS


async def test_web_search_count_zero_uses_valve_default(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    blocks = "".join(_ddg_result_html(f"R{i}", _wrap(f"https://example.com/{i}"), f"s{i}") for i in range(10))
    http_mock.register_ddg(html=blocks)
    tool = _make_tool(http_mock, result_count=3)

    import json

    raw = await tool.web_search("q", count=0, __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    payload = json.loads(raw)
    assert len(payload["results"]) == 3


async def test_web_search_count_override_clamps_to_20(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    blocks = "".join(_ddg_result_html(f"R{i}", _wrap(f"https://example.com/{i}"), f"s{i}") for i in range(25))
    http_mock.register_ddg(html=blocks)
    tool = _make_tool(http_mock)

    import json

    raw = await tool.web_search("q", count=99, __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    payload = json.loads(raw)
    assert len(payload["results"]) == 20


async def test_web_search_handles_network_error(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter, emitted: list
) -> None:
    http_mock.register_ddg_error(httpx.ConnectError("boom"))
    tool = _make_tool(http_mock)

    import json

    raw = await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    payload = json.loads(raw)
    assert "error" in payload
    assert "boom" in payload["error"]
    assert any(ev["type"] == "status" and ev["data"]["status"] == "error" for ev in emitted)


async def test_web_search_concurrent_requests_serialize_via_rate_limit(
    http_mock: HttpMock, fake_request: object, fake_user: dict, emitter
) -> None:
    http_mock.register_ddg(html="")
    tool = _make_tool(http_mock)
    tool.valves.min_request_interval_ms = 120
    tool._rate_limiter.update_interval(120)

    start = time.monotonic()
    await asyncio.gather(
        tool.web_search("a", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter),
        tool.web_search("b", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter),
    )
    elapsed = time.monotonic() - start
    assert elapsed >= 0.10
