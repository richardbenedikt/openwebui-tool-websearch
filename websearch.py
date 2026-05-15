"""
title: Web Search
author: Richard Braun
author_url: https://github.com/richardbenedikt
git_url: https://github.com/richardbenedikt/openwebui-tool-websearch
description: Search the web via DuckDuckGo and fetch pages on demand, with no dependency on OpenWebUI's built-in search.
required_open_webui_version: 0.6.0
requirements: pydantic>=2, httpx>=0.27
version: 3.0.0
license: MIT
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from html import unescape
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from pydantic import BaseModel, Field

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"

_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",  # noqa: E501
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",  # noqa: E501
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",  # noqa: E501
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",  # noqa: E501
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",  # noqa: E501
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",  # noqa: E501
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
)

_BASE_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://duckduckgo.com/",
    "DNT": "1",
}

_SAFE_SEARCH_KP: dict[str, str] = {"strict": "1", "moderate": "-1", "off": "-2"}

_DEFAULT_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
_FETCH_BODY_CHAR_CAP = 20_000
_PARSE_FAILURE_BODY_THRESHOLD = 200
_ANTIBOT_SCAN_WINDOW = 5_000
_RAW_PAYLOAD_PREVIEW_CAP = 1_000

_NAV_LABEL_BLACKLIST: frozenset[str] = frozenset(
    {"here", "more", "privacy", "terms", "settings", "feedback", "help", "next", "previous"}
)

_DDG_HOSTS: frozenset[str] = frozenset({"duckduckgo.com", "duck.co", "html.duckduckgo.com"})

_BLOCK_LEVEL_TAGS: frozenset[str] = frozenset(
    {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}
)
_SKIPPED_TEXT_TAGS: frozenset[str] = frozenset({"script", "style", "noscript", "template", "svg"})

_ANTIBOT_PHRASES: tuple[str, ...] = ("anomaly", "unusual traffic", "captcha")

_SystemRandom = random.SystemRandom()


def _pick_user_agent() -> str:
    return _SystemRandom.choice(_USER_AGENTS)


def _build_headers() -> dict[str, str]:
    headers = dict(_BASE_HEADERS)
    headers["User-Agent"] = _pick_user_agent()
    return headers


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


def _decode_ddg_redirect(href: str) -> str | None:
    if not href:
        return None
    candidate = href.strip()
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if not scheme and not host:
        return None
    if scheme in ("javascript", "mailto", "tel", "data", "ftp"):
        return None

    if host in _DDG_HOSTS:
        if parsed.path == "/l/" and parsed.query:
            params = parse_qs(parsed.query)
            uddg = params.get("uddg", [""])[0]
            if not uddg:
                return None
            decoded = unquote(uddg)
            if decoded.startswith(("http://", "https://")):
                return decoded
        return None

    if scheme in ("http", "https") and host:
        return candidate
    return None


class _ResultParser(HTMLParser):
    """Extract DuckDuckGo HTML search results."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._in_title: bool = False
        self._in_snippet: bool = False
        self._current_href: str = ""
        self._title_buf: list[str] = []
        self._snippet_buf: list[str] = []
        self._pending: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        classes = attr_map.get("class", "").split()
        if tag == "a" and "result__a" in classes:
            self._finalize_pending()
            self._in_title = True
            self._current_href = attr_map.get("href", "")
            self._title_buf = []
            return
        if "result__snippet" in classes and self._pending is not None:
            self._in_snippet = True
            self._snippet_buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag == "a":
            self._in_title = False
            title = _clean_text("".join(self._title_buf))
            self._pending = {"title": title, "href": self._current_href}
            return
        if self._in_snippet and tag in ("a", "div", "span"):
            snippet = _clean_text("".join(self._snippet_buf))
            if self._pending is not None:
                self._pending["snippet"] = snippet
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_buf.append(data)
        elif self._in_snippet:
            self._snippet_buf.append(data)

    def close(self) -> None:
        self._finalize_pending()
        super().close()

    def _finalize_pending(self) -> None:
        if self._pending is None:
            return
        record = self._pending
        self._pending = None
        decoded = _decode_ddg_redirect(record.get("href", ""))
        title = record.get("title", "").strip()
        if not decoded or not title:
            return
        if title.casefold() in _NAV_LABEL_BLACKLIST:
            return
        host = _domain_of(decoded)
        if host in _DDG_HOSTS:
            return
        self.results.append(
            {
                "title": title,
                "link": decoded,
                "snippet": record.get("snippet", "").strip(),
            }
        )


def _clean_text(raw: str) -> str:
    return " ".join(unescape(raw).split())


def _parse_ddg_html(html_text: str) -> list[dict[str, str]]:
    if not html_text:
        return []
    parser = _ResultParser()
    parser.feed(html_text)
    parser.close()
    return _dedupe_by_link(parser.results)


def _dedupe_by_link(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in items:
        link = item.get("link", "")
        if link in seen:
            continue
        seen.add(link)
        out.append(item)
    return out


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML to plain text, dropping script/style content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TEXT_TAGS:
            self._skip_depth += 1
            return
        if tag in _BLOCK_LEVEL_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TEXT_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            self._chunks.append(" ")
            return
        if tag in _BLOCK_LEVEL_TAGS:
            self._chunks.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join("".join(self._chunks).split())


def _strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    extractor = _HTMLTextExtractor()
    extractor.feed(html_text)
    extractor.close()
    return extractor.text()


def _looks_like_antibot(body: str) -> bool:
    window = body[:_ANTIBOT_SCAN_WINDOW].casefold()
    return any(phrase in window for phrase in _ANTIBOT_PHRASES)


class _RateLimiter:
    """Async monotonic-clock gate. One instance per Tools()."""

    def __init__(self, min_interval_ms: int) -> None:
        self._interval = max(0.0, min_interval_ms / 1000.0)
        self._lock = asyncio.Lock()
        self._last_release: float = 0.0

    def update_interval(self, min_interval_ms: int) -> None:
        self._interval = max(0.0, min_interval_ms / 1000.0)

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last_release + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_release = time.monotonic()


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
                "metadata": [{"source": url, "title": title or url, "html": False}],
                "source": {"name": title or url, "url": url},
            },
        }
    )


async def _emit_results_citation(
    emitter: EmitFn | None,
    *,
    query: str,
    results: list[dict[str, Any]],
) -> None:
    """Emit a single bundled citation containing every search result.

    Open WebUI's source-list UI collapses sequences of same-tool citations
    into one chip; bundling all results into a single citation event keeps
    every URL addressable as a sub-source under one search chip.
    """
    if emitter is None or not results:
        return
    documents: list[str] = []
    metadata: list[dict[str, Any]] = []
    for entry in results:
        link = entry.get("link", "")
        title = entry.get("title", "") or link
        snippet = entry.get("snippet", "") or title
        documents.append(snippet)
        metadata.append({"source": link, "title": title, "url": link, "html": False})
    await emitter(
        {
            "type": "citation",
            "data": {
                "document": documents,
                "metadata": metadata,
                "source": {"name": f"Web search: {query}"},
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
        safe_search: Literal["strict", "moderate", "off"] = Field(
            default="moderate",
            description=(
                "DuckDuckGo SafeSearch level. 'moderate' is DDG's own default and the right "
                "choice for general-purpose use; flip to 'off' only if you trust your users."
            ),
        )
        min_request_interval_ms: int = Field(
            default=2000,
            ge=0,
            le=60_000,
            description=(
                "Minimum milliseconds between outbound requests. Lower at your own risk — "
                "DuckDuckGo will rate-limit or captcha-block aggressive scrapers."
            ),
        )
        debug_log_raw_on_parse_failure: bool = Field(
            default=False,
            description=(
                "When the search response is non-empty but yields zero parsed results, "
                "emit a status event with a truncated repr of the raw HTML. Off by default."
            ),
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._rate_limiter = _RateLimiter(self.valves.min_request_interval_ms)
        self._client: httpx.AsyncClient | None = None
        self._client_factory: Callable[[], httpx.AsyncClient] | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
        else:
            self._client = httpx.AsyncClient(
                timeout=_DEFAULT_HTTP_TIMEOUT,
                follow_redirects=True,
                http2=False,
            )
        return self._client

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

        effective_count = self.valves.result_count if count <= 0 else count
        effective_count = max(1, min(20, effective_count))

        self._rate_limiter.update_interval(self.valves.min_request_interval_ms)

        await _emit(__event_emitter__, f"Searching the web for: {cleaned_query}")

        await self._rate_limiter.acquire()
        params = {"q": cleaned_query, "kp": _SAFE_SEARCH_KP[self.valves.safe_search]}
        headers = _build_headers()

        try:
            client = await self._get_client()
            response = await client.get(DDG_ENDPOINT, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            message = f"Web search failed: {exc}"
            await _emit(__event_emitter__, message, done=True, status="error")
            return _error(message)
        except httpx.HTTPError as exc:
            message = f"Web search failed: {exc}"
            await _emit(__event_emitter__, message, done=True, status="error")
            return _error(message)

        body = response.text or ""

        if response.status_code != 200 or _looks_like_antibot(body):
            await _emit(
                __event_emitter__,
                (
                    "DuckDuckGo declined the request (status "
                    f"{response.status_code}); likely rate-limited. "
                    "Consider raising min_request_interval_ms."
                ),
                done=True,
                status="warning",
            )
            return json.dumps(
                {
                    "results": [],
                    "hint": (
                        "DuckDuckGo did not return results — likely rate-limited. "
                        "Inform the user that web search is temporarily unavailable; "
                        "do not retry immediately."
                    ),
                }
            )

        results = _parse_ddg_html(body)

        if not results and len(body.strip()) > _PARSE_FAILURE_BODY_THRESHOLD:
            await _emit(
                __event_emitter__,
                "DuckDuckGo returned an unrecognized response shape; treating as empty.",
                status="warning",
            )
            if self.valves.debug_log_raw_on_parse_failure:
                preview = body
                if len(preview) > _RAW_PAYLOAD_PREVIEW_CAP:
                    preview = preview[:_RAW_PAYLOAD_PREVIEW_CAP] + (f"... [truncated, total {len(body)} chars]")
                await _emit(
                    __event_emitter__,
                    f"Raw backend response: {preview!r}",
                    status="warning",
                )

        results = _filter_results(
            results,
            allow=_split_csv(self.valves.allow_domains),
            block=_split_csv(self.valves.block_domains),
        )
        results = results[:effective_count]

        await _emit_results_citation(__event_emitter__, query=cleaned_query, results=results)

        await _emit(
            __event_emitter__,
            f"Found {len(results)} result(s) for: {cleaned_query}",
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
            payload["hint"] = (
                "These are short snippets. For any non-trivial question — lists, "
                "comparisons, dates, prices, specs, multi-step instructions — call "
                "fetch_url on the most relevant link(s) before answering. Do not "
                "rely on snippets alone."
            )
        return json.dumps(payload)

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

        self._rate_limiter.update_interval(self.valves.min_request_interval_ms)
        await _emit(__event_emitter__, f"Fetching {cleaned_url}")
        await self._rate_limiter.acquire()

        headers = _build_headers()
        try:
            client = await self._get_client()
            response = await client.get(cleaned_url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            message = f"Fetch failed: {exc}"
            await _emit(__event_emitter__, message, done=True, status="error")
            return _error(message)

        content_type = response.headers.get("content-type", "").lower()
        if content_type.startswith(("text/html", "application/xhtml")):
            text = _strip_html(response.text)
        elif content_type.startswith("text/"):
            text = response.text
        else:
            await _emit(
                __event_emitter__,
                f"Non-text content-type '{content_type or 'unknown'}'; returning empty body.",
                status="warning",
            )
            text = ""

        truncated = False
        if len(text) > _FETCH_BODY_CHAR_CAP:
            text = text[:_FETCH_BODY_CHAR_CAP] + "... [truncated]"
            truncated = True

        await _emit_citation(__event_emitter__, url=cleaned_url, title=cleaned_url, content=text)
        await _emit(
            __event_emitter__,
            (f"Fetched {len(text)} character(s) from {host}" + (" (truncated)" if truncated else "")),
            done=True,
            status="success" if text else "warning",
        )
        return json.dumps({"url": cleaned_url, "content": text})
