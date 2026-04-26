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
    assert "fetch_url" in payload["hint"]
    assert search_calls and search_calls[0]["query"] == "openwebui"
    assert search_calls[0]["count"] == tool.valves.result_count
    assert any(e["data"].get("done") for e in emitted if e.get("type") == "status")


async def test_web_search_warns_on_unrecognized_response_shape(
    patch_builtins, fake_request, fake_user, emitter, emitted
) -> None:
    patch_builtins(search_result={"data": [{"title": "x", "link": "https://x/1"}]})
    tool = _make_tool()
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    payload = json.loads(out)
    assert payload["results"] == []
    statuses = [e for e in emitted if e.get("type") == "status"]
    assert any(
        e["data"].get("status") == "warning" and "unrecognized" in e["data"].get("description", "").lower()
        for e in statuses
    )


async def test_web_search_emits_retry_hint_when_no_results(patch_builtins, fake_request, fake_user) -> None:
    patch_builtins(search_result=[])
    tool = _make_tool()
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert payload["results"] == []
    hint = payload["hint"].lower()
    assert "broader" in hint or "shorter" in hint
    assert "web_search" in hint


async def test_web_search_omits_hint_when_fetch_url_disabled(patch_builtins, fake_request, fake_user) -> None:
    patch_builtins(search_result=[{"title": "T", "link": "https://x/1", "snippet": "s"}])
    tool = _make_tool(enable_fetch_url=False)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert payload["results"]
    assert "hint" not in payload


async def test_web_search_auto_fetch_top_embeds_content(patch_builtins, fake_request, fake_user) -> None:
    _, fetch_calls = patch_builtins(
        search_result=[
            {"title": "A", "link": "https://a.test/1", "snippet": "sa"},
            {"title": "B", "link": "https://b.test/2", "snippet": "sb"},
            {"title": "C", "link": "https://c.test/3", "snippet": "sc"},
        ],
        fetch_result="full page body",
    )
    tool = _make_tool(auto_fetch_top=2)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert payload["results"][0]["content"] == "full page body"
    assert payload["results"][1]["content"] == "full page body"
    assert "content" not in payload["results"][2]
    assert len(fetch_calls) == 2
    assert "pre-fetched" in payload["hint"] or "fetched" in payload["hint"]


async def test_web_search_auto_fetch_top_zero_fetches_all(patch_builtins, fake_request, fake_user) -> None:
    _, fetch_calls = patch_builtins(
        search_result=[
            {"title": "A", "link": "https://a.test/1", "snippet": "sa"},
            {"title": "B", "link": "https://b.test/2", "snippet": "sb"},
            {"title": "C", "link": "https://c.test/3", "snippet": "sc"},
        ],
        fetch_result="full page body",
    )
    tool = _make_tool(auto_fetch_top=0)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert all(r["content"] == "full page body" for r in payload["results"])
    assert len(fetch_calls) == 3
    assert "pre-fetched" in payload["hint"] or "already been fetched" in payload["hint"]


async def test_web_search_auto_fetch_disabled_skips_prefetch(patch_builtins, fake_request, fake_user) -> None:
    _, fetch_calls = patch_builtins(
        search_result=[{"title": "A", "link": "https://a.test/1", "snippet": "sa"}],
        fetch_result="should not be called",
    )
    tool = _make_tool(auto_fetch_enabled=False)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert "content" not in payload["results"][0]
    assert fetch_calls == []
    assert "fetch_url" in payload["hint"]


async def test_fetch_url_still_works_when_auto_fetch_disabled(patch_builtins, fake_request, fake_user) -> None:
    _, fetch_calls = patch_builtins(fetch_result="hello")
    tool = _make_tool(auto_fetch_enabled=False)
    out = await tool.fetch_url("https://example.com/x", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert payload["content"] == "hello"
    assert len(fetch_calls) == 1


async def test_web_search_auto_fetch_top_inactive_when_fetch_url_disabled(
    patch_builtins, fake_request, fake_user
) -> None:
    _, fetch_calls = patch_builtins(
        search_result=[{"title": "A", "link": "https://a.test/1", "snippet": "sa"}],
        fetch_result="x",
    )
    tool = _make_tool(auto_fetch_top=3, enable_fetch_url=False)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert "content" not in payload["results"][0]
    assert fetch_calls == []
    assert "hint" not in payload


async def test_web_search_auto_fetch_emits_citation_per_page(
    patch_builtins, fake_request, fake_user, emitter, emitted
) -> None:
    patch_builtins(
        search_result=[
            {"title": "T1", "link": "https://a.test/1", "snippet": "s1"},
            {"title": "T2", "link": "https://b.test/2", "snippet": "s2"},
        ],
        fetch_result="body",
    )
    tool = _make_tool()
    await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    citations = [e for e in emitted if e.get("type") == "citation"]
    assert len(citations) == 2
    urls = {c["data"]["source"]["url"] for c in citations}
    assert urls == {"https://a.test/1", "https://b.test/2"}
    assert all(c["data"]["document"] == ["body"] for c in citations)
    names = {c["data"]["source"]["name"] for c in citations}
    assert names == {"T1", "T2"}


async def test_web_search_auto_fetch_skips_citation_on_empty_body(
    patch_builtins, fake_request, fake_user, emitter, emitted
) -> None:
    patch_builtins(
        search_result=[{"title": "T", "link": "https://a.test/1", "snippet": "s"}],
        fetch_result="",
    )
    tool = _make_tool()
    await tool.web_search("q", __request__=fake_request, __user__=fake_user, __event_emitter__=emitter)
    citations = [e for e in emitted if e.get("type") == "citation"]
    assert citations == []


async def test_fetch_url_emits_citation(patch_builtins, fake_request, fake_user, emitter, emitted) -> None:
    patch_builtins(fetch_result="hello")
    tool = _make_tool()
    await tool.fetch_url(
        "https://example.com/x",
        __request__=fake_request,
        __user__=fake_user,
        __event_emitter__=emitter,
    )
    citations = [e for e in emitted if e.get("type") == "citation"]
    assert len(citations) == 1
    assert citations[0]["data"]["source"]["url"] == "https://example.com/x"
    assert citations[0]["data"]["document"] == ["hello"]


async def test_web_search_auto_fetch_records_errors(patch_builtins, fake_request, fake_user) -> None:
    patch_builtins(
        search_result=[{"title": "A", "link": "https://a.test/1", "snippet": "sa"}],
        fetch_result=RuntimeError("boom"),
    )
    tool = _make_tool(auto_fetch_top=1)
    out = await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    payload = json.loads(out)
    assert payload["results"][0].get("fetch_error") == "boom"
    assert "content" not in payload["results"][0]


async def test_web_search_auto_fetch_caps_at_results_length(patch_builtins, fake_request, fake_user) -> None:
    _, fetch_calls = patch_builtins(
        search_result=[{"title": "A", "link": "https://a.test/1", "snippet": "sa"}],
        fetch_result="ok",
    )
    tool = _make_tool(auto_fetch_top=5)
    await tool.web_search("q", __request__=fake_request, __user__=fake_user)
    assert len(fetch_calls) == 1


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
    assert doc.startswith("Fetch the full text of a specific URL")


def test_citation_is_class_attribute() -> None:
    assert Tools.citation is False
    assert "citation" not in Tools().__dict__
