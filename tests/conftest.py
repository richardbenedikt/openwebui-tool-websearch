from __future__ import annotations

import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def fake_request() -> object:
    return types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace()))


@pytest.fixture
def fake_user() -> dict[str, Any]:
    return {"id": "test-user", "role": "user", "valves": {}}


@pytest.fixture
def emitted() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def emitter(emitted: list[dict[str, Any]]) -> Callable[[dict[str, Any]], Any]:
    async def _emit(event: dict[str, Any]) -> None:
        emitted.append(event)

    return _emit


@pytest.fixture(autouse=True)
def _fast_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every Tools() in tests to a 0ms throttle so the suite doesn't sleep."""
    import websearch

    original_init = websearch.Tools.__init__

    def _patched(self: Any) -> None:
        original_init(self)
        self.valves.min_request_interval_ms = 0
        self._rate_limiter.update_interval(0)

    monkeypatch.setattr(websearch.Tools, "__init__", _patched)


class HttpMock:
    """Mounts an httpx.MockTransport on a Tools instance and records traffic."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}
        self.requests_seen: list[httpx.Request] = []

    def _dispatch(self, request: httpx.Request) -> httpx.Response:
        self.requests_seen.append(request)
        path_key = (request.method, f"{request.url.scheme}://{request.url.host}{request.url.path}")
        if path_key in self._handlers:
            return self._handlers[path_key](request)
        full_key = (request.method, str(request.url))
        if full_key in self._handlers:
            return self._handlers[full_key](request)
        return httpx.Response(404, text=f"unmatched: {request.url}")

    def factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._dispatch), timeout=5.0)

    def register_ddg(self, *, html: str, status: int = 200) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status,
                text=html,
                headers={"content-type": "text/html; charset=utf-8"},
            )

        self._handlers[("GET", "https://html.duckduckgo.com/html/")] = handler

    def register_ddg_error(self, exc: Exception) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            raise exc

        self._handlers[("GET", "https://html.duckduckgo.com/html/")] = handler

    def register_fetch(
        self,
        url: str,
        *,
        body: str,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text=body, headers={"content-type": content_type})

        self._handlers[("GET", url)] = handler

    def register_fetch_error(self, url: str, *, exc: Exception) -> None:
        def handler(_req: httpx.Request) -> httpx.Response:
            raise exc

        self._handlers[("GET", url)] = handler


@pytest.fixture
def http_mock() -> HttpMock:
    return HttpMock()
