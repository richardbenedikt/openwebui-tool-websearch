from __future__ import annotations

import json
from typing import Any

import pytest

import websearch
from websearch import Tools


def _make_tool(**valve_overrides: Any) -> Tools:
    tool = Tools()
    for key, value in valve_overrides.items():
        setattr(tool.valves, key, value)
    return tool


async def test_web_search_returns_json_results(patch_builtins, fake_request, fake_user, emitter, emitted) -> None:
    search_calls, _ = patch_builtins(
        search_result=[
            {"title": "First", "link": "https://example.com/1", "snippet": "s1"},
            {"title": "Second", "link": "https://other.org/2", "snippet": "s2"},
        ]
    )
    tool = _make_tool()
    out = await tool.web_search(
        "openwebui",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )
    payload = json.loads(out)
    assert "results" in payload
    assert len(payload["results"]) == 2
    assert payload["results"][0]["link"] == "https://example.com/1"
    assert search_calls and search_calls[0]["query"] == "openwebui"
    assert search_calls[0]["count"] == tool.valves.result_count
    assert any(e["data"]["done"] for e in emitted)


async def test_web_search_count_override_clamps(patch_builtins, fake_request, fake_user) -> None:
    search_calls, _ = patch_builtins(
        search_result=[{"title": str(i), "link": f"https://x/{i}", "snippet": ""} for i in range(25)]
    )
    tool = _make_tool()
    out = await tool.web_search("q", count=999, __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert len(payload["results"]) == 20
    assert search_calls[0]["count"] == 20


async def test_web_search_count_zero_uses_valve(patch_builtins, fake_request, fake_user) -> None:
    search_calls, _ = patch_builtins(
        search_result=[{"title": str(i), "link": f"https://x/{i}", "snippet": ""} for i in range(10)]
    )
    tool = _make_tool(result_count=3)
    out = await tool.web_search("q", count=0, __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert len(payload["results"]) == 3
    assert search_calls[0]["count"] == 3


async def test_web_search_applies_block_filter(patch_builtins, fake_request, fake_user) -> None:
    patch_builtins(
        search_result=[
            {"title": "A", "link": "https://blocked.com/1", "snippet": ""},
            {"title": "B", "link": "https://allowed.com/2", "snippet": ""},
        ]
    )
    tool = _make_tool(block_domains="blocked.com")
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert [r["link"] for r in payload["results"]] == ["https://allowed.com/2"]


async def test_web_search_passes_query_through_unchanged(patch_builtins, fake_request, fake_user) -> None:
    search_calls, _ = patch_builtins(search_result=[])
    tool = _make_tool()
    await tool.web_search("hallo welt", __request__=fake_request, __user__=fake_user)
    assert search_calls[0]["query"] == "hallo welt"


async def test_web_search_empty_query_returns_error(fake_request, fake_user) -> None:
    tool = _make_tool()
    out = await tool.web_search("   ", __request__=fake_request, __user__=fake_user)
    assert json.loads(out) == {"error": "Query must not be empty."}


async def test_web_search_missing_request_returns_error() -> None:
    tool = _make_tool()
    out = await tool.web_search("q")
    assert "error" in json.loads(out)


async def test_web_search_handles_backend_failure(patch_builtins, fake_request, fake_user, emitter, emitted) -> None:
    patch_builtins(search_result=RuntimeError("boom"))
    tool = _make_tool()
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    payload = json.loads(out)
    assert "error" in payload and "boom" in payload["error"]
    assert emitted[-1]["data"]["status"] == "error"


async def test_web_search_handles_resolver_failure(monkeypatch: pytest.MonkeyPatch, fake_request, fake_user) -> None:
    monkeypatch.setattr(
        websearch,
        "_resolve_builtins",
        lambda: (_ for _ in ()).throw(RuntimeError("no builtins")),
    )
    tool = _make_tool()
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    assert "no builtins" in json.loads(out)["error"]


async def test_fetch_url_returns_content(patch_builtins, fake_request, fake_user, emitter, emitted) -> None:
    _, fetch_calls = patch_builtins(fetch_result="hello world")
    tool = _make_tool()
    out = await tool.fetch_url(
        "https://example.com/page",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )
    payload = json.loads(out)
    assert payload["content"] == "hello world"
    assert payload["url"] == "https://example.com/page"
    assert fetch_calls and fetch_calls[0]["url"] == "https://example.com/page"
    assert emitted[-1]["data"]["done"] is True


async def test_fetch_url_disabled_by_valve(fake_request, fake_user) -> None:
    tool = _make_tool(enable_fetch_url=False)
    out = await tool.fetch_url("https://example.com/page", __request__=fake_request, __user__=fake_user)
    assert "disabled" in json.loads(out)["error"]


async def test_fetch_url_rejects_non_http_scheme(fake_request, fake_user) -> None:
    tool = _make_tool()
    out = await tool.fetch_url("file:///etc/passwd", __request__=fake_request, __user__=fake_user)
    assert "http(s)" in json.loads(out)["error"]


async def test_fetch_url_respects_block_list(patch_builtins, fake_request, fake_user) -> None:
    patch_builtins(fetch_result="should not be returned")
    tool = _make_tool(block_domains="example.com")
    out = await tool.fetch_url("https://example.com/x", __request__=fake_request, __user__=fake_user)
    assert "blocklist" in json.loads(out)["error"]


async def test_fetch_url_respects_allow_list(patch_builtins, fake_request, fake_user) -> None:
    patch_builtins(fetch_result="ok")
    tool = _make_tool(allow_domains="other.org")
    out = await tool.fetch_url("https://example.com/x", __request__=fake_request, __user__=fake_user)
    assert "allowlist" in json.loads(out)["error"]


def test_web_search_docstring_starts_with_when_to_call() -> None:
    doc = (Tools.web_search.__doc__ or "").strip()
    assert doc.startswith("Search the web when"), "First sentence drives LLM call gating; do not weaken it."


def test_fetch_url_docstring_starts_with_when_to_call() -> None:
    doc = (Tools.fetch_url.__doc__ or "").strip()
    assert doc.startswith("Fetch the full text of a specific URL when")


def test_citation_is_class_attribute() -> None:
    assert Tools.citation is False
    assert "citation" not in Tools().__dict__
