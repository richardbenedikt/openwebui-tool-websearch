from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from tests.conftest import HttpMock
from websearch import Tools


def _make_tool(http_mock: HttpMock | None = None, **valve_overrides: Any) -> Tools:
    tool = Tools()
    if http_mock is not None:
        tool._client_factory = http_mock.factory
    for key, value in valve_overrides.items():
        setattr(tool.valves, key, value)
    return tool


def _ddg_result_html(title: str, href: str, snippet: str = "snip") -> str:
    return (
        f'<div class="result results_links">'
        f'  <h2><a class="result__a" href="{href}">{title}</a></h2>'
        f'  <a class="result__snippet">{snippet}</a>'
        f"</div>"
    )


def _wrap(target: str) -> str:
    return f"//duckduckgo.com/l/?uddg={quote(target, safe='')}"


async def test_web_search_returns_json_results(http_mock: HttpMock, fake_request, fake_user, emitter, emitted) -> None:
    page = (
        "<html><body>"
        + (
            _ddg_result_html("First", _wrap("https://example.com/1"), "s1")
            + _ddg_result_html("Second", _wrap("https://other.org/2"), "s2")
        )
        + "</body></html>"
    )
    http_mock.register_ddg(html=page)

    tool = _make_tool(http_mock)
    out = await tool.web_search("openwebui", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    payload = json.loads(out)
    assert len(payload["results"]) == 2
    assert payload["results"][0]["link"] == "https://example.com/1"
    assert payload["results"][0]["title"] == "First"
    assert "fetch_url" in payload["hint"]
    assert http_mock.requests_seen[0].url.params["q"] == "openwebui"
    assert any(e["data"].get("done") for e in emitted if e.get("type") == "status")


async def test_web_search_warns_on_unrecognized_response_shape(
    http_mock: HttpMock, fake_request, fake_user, emitter, emitted
) -> None:
    http_mock.register_ddg(html="<html><body>" + ("x" * 300) + "</body></html>")
    tool = _make_tool(http_mock)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    payload = json.loads(out)
    assert payload["results"] == []
    statuses = [e for e in emitted if e.get("type") == "status"]
    assert any(
        s["data"].get("status") == "warning" and "unrecognized" in s["data"].get("description", "").lower()
        for s in statuses
    )
    assert not any("raw backend response" in s["data"].get("description", "").lower() for s in statuses)


async def test_web_search_debug_emits_raw_payload_when_valve_on(
    http_mock: HttpMock, fake_request, fake_user, emitter, emitted
) -> None:
    body = "<html><body>" + ("x" * 300) + "marker_123</body></html>"
    http_mock.register_ddg(html=body)
    tool = _make_tool(http_mock, debug_log_raw_on_parse_failure=True)
    await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    statuses = [e for e in emitted if e.get("type") == "status"]
    raw_emits = [s for s in statuses if "raw backend response" in s["data"].get("description", "").lower()]
    assert len(raw_emits) == 1
    assert "marker_123" in raw_emits[0]["data"]["description"]


async def test_web_search_debug_truncates_long_raw_payload(
    http_mock: HttpMock, fake_request, fake_user, emitter, emitted
) -> None:
    body = "<html>" + ("y" * 5000) + "</html>"
    http_mock.register_ddg(html=body)
    tool = _make_tool(http_mock, debug_log_raw_on_parse_failure=True)
    await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    statuses = [e for e in emitted if e.get("type") == "status"]
    raw_emits = [s for s in statuses if "raw backend response" in s["data"].get("description", "").lower()]
    assert len(raw_emits) == 1
    desc = raw_emits[0]["data"]["description"]
    assert "truncated" in desc
    assert len(desc) < 1500


async def test_web_search_debug_silent_when_body_is_tiny(
    http_mock: HttpMock, fake_request, fake_user, emitter, emitted
) -> None:
    http_mock.register_ddg(html="<html></html>")
    tool = _make_tool(http_mock, debug_log_raw_on_parse_failure=True)
    await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    statuses = [e for e in emitted if e.get("type") == "status"]
    assert not any("raw backend response" in s["data"].get("description", "").lower() for s in statuses)
    assert not any("unrecognized" in s["data"].get("description", "").lower() for s in statuses)


async def test_web_search_emits_retry_hint_when_no_results(http_mock: HttpMock, fake_request, fake_user) -> None:
    http_mock.register_ddg(html="")
    tool = _make_tool(http_mock)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert payload["results"] == []
    hint = payload["hint"].lower()
    assert "broader" in hint or "shorter" in hint
    assert "web_search" in hint


async def test_web_search_omits_hint_when_fetch_url_disabled(http_mock: HttpMock, fake_request, fake_user) -> None:
    page = _ddg_result_html("T", _wrap("https://x.example/1"))
    http_mock.register_ddg(html=page)
    tool = _make_tool(http_mock, enable_fetch_url=False)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert payload["results"]
    assert "hint" not in payload


async def test_web_search_applies_block_filter(http_mock: HttpMock, fake_request, fake_user) -> None:
    page = _ddg_result_html("Blocked", _wrap("https://blocked.com/1")) + _ddg_result_html(
        "Allowed", _wrap("https://allowed.com/2")
    )
    http_mock.register_ddg(html=page)
    tool = _make_tool(http_mock, block_domains="blocked.com")
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert [r["link"] for r in payload["results"]] == ["https://allowed.com/2"]


async def test_web_search_emits_bundled_citation(
    http_mock: HttpMock, fake_request, fake_user, emitter, emitted
) -> None:
    page = _ddg_result_html("Alpha", _wrap("https://a.example/1"), "snippet alpha") + _ddg_result_html(
        "Bravo", _wrap("https://b.example/2"), "snippet bravo"
    )
    http_mock.register_ddg(html=page)
    tool = _make_tool(http_mock)
    await tool.web_search("nintendo", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    citations = [e for e in emitted if e.get("type") == "citation"]
    assert len(citations) == 1
    data = citations[0]["data"]
    assert data["document"] == ["snippet alpha", "snippet bravo"]
    assert [m["source"] for m in data["metadata"]] == ["https://a.example/1", "https://b.example/2"]
    assert [m["title"] for m in data["metadata"]] == ["Alpha", "Bravo"]
    assert "nintendo" in data["source"]["name"]


async def test_web_search_emits_no_citation_on_empty_results(
    http_mock: HttpMock, fake_request, fake_user, emitter, emitted
) -> None:
    http_mock.register_ddg(html="")
    tool = _make_tool(http_mock)
    await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    citations = [e for e in emitted if e.get("type") == "citation"]
    assert citations == []


async def test_web_search_empty_query_returns_error(fake_request, fake_user) -> None:
    tool = _make_tool()
    out = await tool.web_search("   ", __request__=fake_request, __user__=fake_user)
    assert json.loads(out) == {"error": "Query must not be empty."}


async def test_fetch_url_returns_content(http_mock: HttpMock, fake_request, fake_user, emitter, emitted) -> None:
    http_mock.register_fetch(
        "https://example.com/page",
        body="<html><body><p>hello world</p></body></html>",
    )
    tool = _make_tool(http_mock)
    out = await tool.fetch_url(
        "https://example.com/page",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )
    payload = json.loads(out)
    assert "hello world" in payload["content"]
    assert payload["url"] == "https://example.com/page"
    assert emitted[-1]["data"]["done"] is True


async def test_fetch_url_disabled_by_valve(fake_request, fake_user) -> None:
    tool = _make_tool(enable_fetch_url=False)
    out = await tool.fetch_url("https://example.com/page", __request__=fake_request, __user__=fake_user)
    assert "disabled" in json.loads(out)["error"]


async def test_fetch_url_rejects_non_http_scheme(fake_request, fake_user) -> None:
    tool = _make_tool()
    out = await tool.fetch_url("file:///etc/passwd", __request__=fake_request, __user__=fake_user)
    assert "http(s)" in json.loads(out)["error"]


async def test_fetch_url_respects_block_list(fake_request, fake_user) -> None:
    tool = _make_tool(block_domains="example.com")
    out = await tool.fetch_url("https://example.com/x", __request__=fake_request, __user__=fake_user)
    assert "blocklist" in json.loads(out)["error"]


async def test_fetch_url_respects_allow_list(fake_request, fake_user) -> None:
    tool = _make_tool(allow_domains="other.org")
    out = await tool.fetch_url("https://example.com/x", __request__=fake_request, __user__=fake_user)
    assert "allowlist" in json.loads(out)["error"]


def test_web_search_docstring_starts_with_when_to_call() -> None:
    doc = (Tools.web_search.__doc__ or "").strip()
    assert doc.startswith("Search the web when"), "First sentence drives LLM call gating; do not weaken it."


def test_fetch_url_docstring_starts_with_when_to_call() -> None:
    doc = (Tools.fetch_url.__doc__ or "").strip()
    assert doc.startswith("Fetch the full text of a specific URL")


def test_citation_is_class_attribute() -> None:
    assert Tools.citation is False
    assert "citation" not in Tools().__dict__
