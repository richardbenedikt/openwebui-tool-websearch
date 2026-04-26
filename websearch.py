"""
title: Web Search
author: Richard Braun
author_url: https://github.com/richardbenedikt
git_url: https://github.com/richardbenedikt/openwebui-tool-websearch
description: Search the web and fetch pages on demand, via OpenWebUI's configured backend.
required_open_webui_version: 0.6.0
requirements: pydantic>=2
version: 2.2.0
license: MIT
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable
from importlib import import_module
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

_BUILTIN_MODULE_CANDIDATES: tuple[str, ...] = (
    "open_webui.tools.builtin",
    "open_webui.utils.tools.builtin",
)

_MIN_VERSION_HINT = "0.6.0"


def _resolve_builtins() -> tuple[Callable[..., Awaitable[str]], Callable[..., Awaitable[str]]]:
    last_error: Exception | None = None
    for path in _BUILTIN_MODULE_CANDIDATES:
        try:
            module = import_module(path)
        except ImportError as exc:
            last_error = exc
            continue
        search = getattr(module, "search_web", None)
        fetch = getattr(module, "fetch_url", None)
        if callable(search) and callable(fetch):
            return search, fetch
    raise RuntimeError(
        f"This tool requires OpenWebUI >= {_MIN_VERSION_HINT} with builtin "
        f"search_web/fetch_url. Last import error: {last_error!r}"
    )


def _split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower()


def _matches_any(host: str, patterns: Iterable[str]) -> bool:
    if not host:
        return False
    return any(host == pattern or host.endswith("." + pattern) for pattern in patterns)


def _filter_results(results: list[dict[str, Any]], allow: list[str], block: list[str]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in results:
        host = _domain_of(str(item.get("link", "")))
        if allow and not _matches_any(host, allow):
            continue
        if block and _matches_any(host, block):
            continue
        filtered.append(item)
    return filtered


def _looks_empty(raw: Any) -> bool:
    """True if `raw` plausibly represents an empty result set in a recognized shape.

    Used to distinguish a backend that genuinely returned nothing from one whose
    response shape we failed to parse — the latter deserves a diagnostic warning,
    the former does not.
    """
    if raw is None:
        return True
    if isinstance(raw, str):
        if not raw.strip():
            return True
        try:
            return _looks_empty(json.loads(raw))
        except json.JSONDecodeError:
            return False
    if isinstance(raw, list):
        return len(raw) == 0
    if isinstance(raw, dict):
        if not raw:
            return True
        results = raw.get("results")
        return isinstance(results, list) and len(results) == 0
    return False


def _normalize(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        parsed = raw
    if isinstance(parsed, dict):
        if "results" in parsed and isinstance(parsed["results"], list):
            parsed = parsed["results"]
        else:
            return []
    if not isinstance(parsed, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        normalized.append(
            {
                "title": str(entry.get("title", "") or ""),
                "link": str(entry.get("link", entry.get("url", "")) or ""),
                "snippet": str(entry.get("snippet", entry.get("content", "")) or ""),
            }
        )
    return normalized


async def _emit(emitter: EmitFn | None, description: str, *, done: bool = False, status: str = "in_progress") -> None:
    if emitter is None:
        return
    await emitter(
        {
            "type": "status",
            "data": {"status": status, "description": description, "done": done},
        }
    )


async def _emit_citation(emitter: EmitFn | None, *, url: str, title: str, content: str) -> None:
    if emitter is None or not content:
        return
    await emitter(
        {
            "type": "citation",
            "data": {
                "document": [content],
                "metadata": [{"source": url}],
                "source": {"name": title or url, "url": url},
            },
        }
    )


def _error(message: str) -> str:
    return json.dumps({"error": message})


class Tools:
    """OpenWebUI tool that exposes web_search and fetch_url to the model."""

    citation: bool = False

    class Valves(BaseModel):
        result_count: int = Field(
            default=5,
            ge=1,
            le=20,
            description="Default number of search results returned to the model (1-20).",
        )
        allow_domains: str = Field(
            default="",
            description=(
                "Comma-separated allowlist of domains. When set, only results "
                "from these domains (or subdomains) are returned. Empty disables the filter."
            ),
        )
        block_domains: str = Field(
            default="",
            description="Comma-separated blocklist of domains (and subdomains).",
        )
        enable_fetch_url: bool = Field(
            default=True,
            description="Master switch for the fetch_url method.",
        )
        auto_fetch_enabled: bool = Field(
            default=True,
            description=(
                "Master switch for the post-search auto-fetch step. When false, "
                "web_search returns snippets only, but the model can still call "
                "fetch_url itself (unlike enable_fetch_url, which disables fetch_url "
                "entirely)."
            ),
        )
        auto_fetch_top: int = Field(
            default=0,
            ge=0,
            le=20,
            description=(
                "When auto_fetch_enabled is true, controls how many pages are "
                "pre-fetched per search. 0 (default) fetches every returned result; "
                "a positive N fetches only the top N (capped at the number of "
                "returned results)."
            ),
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def web_search(
        self,
        query: str,
        count: int = 0,
        __request__: Any = None,
        __user__: dict[str, Any] | None = None,
        __event_emitter__: EmitFn | None = None,
    ) -> str:
        """
        Search the web when the user's question requires current, recent,
        or post-training-cutoff information, or specific facts you do not
        reliably know. Call multiple times with refined queries if the first
        results are insufficient. If a call returns no results, retry with a
        broader query (drop the year, drop adjectives, keep 2-4 core terms)
        before declining to answer — search engines frequently miss long,
        over-specified phrases. After results come back, call fetch_url on
        one or more of the most relevant links to read the full page before
        answering — snippets are short and frequently misleading, especially
        for lists, comparisons, dates, prices, or specifications. Do not
        call for general knowledge, math, or topics fully covered by your
        training data.

        :param query: A focused search query in natural language.
        :param count: Optional override for number of results (1-20). 0 uses the configured default.
        :return: JSON string {"results": [...], "hint": "..."} or {"error": "..."}.
        """
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return _error("Query must not be empty.")

        if __request__ is None:
            return _error("Request context not available.")

        try:
            search_web, _ = _resolve_builtins()
        except RuntimeError as exc:
            await _emit(__event_emitter__, str(exc), done=True, status="error")
            return _error(str(exc))

        effective_count = self.valves.result_count if count <= 0 else count
        effective_count = max(1, min(20, effective_count))

        await _emit(__event_emitter__, f"Searching the web for: {cleaned_query}")

        try:
            raw = await search_web(
                query=cleaned_query,
                count=effective_count,
                __request__=__request__,
                __user__=__user__,
            )
        except Exception as exc:
            message = f"Web search failed: {exc}"
            await _emit(__event_emitter__, message, done=True, status="error")
            return _error(message)

        results = _normalize(raw)
        if not results and not _looks_empty(raw):
            await _emit(
                __event_emitter__,
                "Search backend returned an unrecognized response shape; treating as empty.",
                status="warning",
            )
        results = _filter_results(
            results,
            allow=_split_csv(self.valves.allow_domains),
            block=_split_csv(self.valves.block_domains),
        )
        results = results[:effective_count]

        fetched_count = 0
        if results and self.valves.enable_fetch_url and self.valves.auto_fetch_enabled:
            fetched_count = await self._auto_fetch(
                results, __request__=__request__, __user__=__user__, emitter=__event_emitter__
            )

        await _emit(
            __event_emitter__,
            f"Found {len(results)} result(s) for: {cleaned_query}"
            + (f" ({fetched_count} pre-fetched)" if fetched_count else ""),
            done=True,
            status="success" if results else "warning",
        )
        payload: dict[str, Any] = {"results": results}
        if not results:
            payload["hint"] = (
                "No results returned. The search engine often misses long, "
                "over-specified queries. Call web_search again with a shorter, "
                "broader query — drop the year, drop adjectives, keep 2-4 core "
                "terms — before telling the user you don't know."
            )
        elif self.valves.enable_fetch_url:
            if fetched_count:
                payload["hint"] = (
                    f"The top {fetched_count} page(s) have already been fetched and are "
                    "included as 'content' on each result. Read those bodies directly to "
                    "answer; you do not need to call fetch_url for them. Call fetch_url "
                    "only for additional links that were not pre-fetched."
                )
            else:
                payload["hint"] = (
                    "These are short snippets. For any non-trivial question — lists, "
                    "comparisons, dates, prices, specs, multi-step instructions — call "
                    "fetch_url on the most relevant link(s) before answering. Do not "
                    "rely on snippets alone."
                )
        return json.dumps(payload)

    async def _auto_fetch(
        self,
        results: list[dict[str, Any]],
        *,
        __request__: Any,
        __user__: dict[str, Any] | None,
        emitter: EmitFn | None,
    ) -> int:
        try:
            _, fetch_url = _resolve_builtins()
        except RuntimeError:
            return 0

        limit = self.valves.auto_fetch_top
        top = results if limit == 0 else results[:limit]
        if not top:
            return 0

        await _emit(emitter, f"Pre-fetching top {len(top)} page(s)...")

        async def _one(entry: dict[str, Any]) -> None:
            link = str(entry.get("link", ""))
            if not link:
                return
            try:
                content = await fetch_url(url=link, __request__=__request__, __user__=__user__)
                text = content if isinstance(content, str) else ""
                entry["content"] = text
                await _emit_citation(emitter, url=link, title=str(entry.get("title") or ""), content=text)
            except Exception as exc:
                entry["fetch_error"] = str(exc)

        await asyncio.gather(*(_one(entry) for entry in top), return_exceptions=False)
        return sum(1 for entry in top if "content" in entry)

    async def fetch_url(
        self,
        url: str,
        __request__: Any = None,
        __user__: dict[str, Any] | None = None,
        __event_emitter__: EmitFn | None = None,
    ) -> str:
        """
        Fetch the full text of a specific URL when web_search has returned
        candidate links. You should call this on at least one — usually two
        or three — of the top results before answering any non-trivial
        question. Snippets from search are short and often misleading;
        the page body is the source of truth. Do not call without first
        having a URL from web_search results or directly from the user.

        :param url: The absolute http(s) URL to fetch.
        :return: JSON string {"url": "...", "content": "..."} or {"error": "..."}.
        """
        if not self.valves.enable_fetch_url:
            return _error("fetch_url is disabled by the administrator.")

        cleaned_url = (url or "").strip()
        if not cleaned_url:
            return _error("URL must not be empty.")

        parsed = urlparse(cleaned_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return _error("Only absolute http(s) URLs are supported.")

        host = parsed.hostname.lower()
        allow = _split_csv(self.valves.allow_domains)
        block = _split_csv(self.valves.block_domains)
        if allow and not _matches_any(host, allow):
            return _error(f"Host '{host}' is not in the allowlist.")
        if block and _matches_any(host, block):
            return _error(f"Host '{host}' is in the blocklist.")

        if __request__ is None:
            return _error("Request context not available.")

        try:
            _, fetch_url = _resolve_builtins()
        except RuntimeError as exc:
            await _emit(__event_emitter__, str(exc), done=True, status="error")
            return _error(str(exc))

        await _emit(__event_emitter__, f"Fetching {cleaned_url}")

        try:
            content = await fetch_url(
                url=cleaned_url,
                __request__=__request__,
                __user__=__user__,
            )
        except Exception as exc:
            message = f"Fetch failed: {exc}"
            await _emit(__event_emitter__, message, done=True, status="error")
            return _error(message)

        text = content if isinstance(content, str) else ""
        await _emit_citation(__event_emitter__, url=cleaned_url, title=cleaned_url, content=text)
        await _emit(
            __event_emitter__,
            f"Fetched {len(text)} character(s) from {host}",
            done=True,
            status="success" if text else "warning",
        )
        return json.dumps({"url": cleaned_url, "content": text})
