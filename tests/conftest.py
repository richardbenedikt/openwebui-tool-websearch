from __future__ import annotations

import json
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


@pytest.fixture
def patch_builtins(monkeypatch: pytest.MonkeyPatch):
    """Patch _resolve_builtins on the websearch module with caller-supplied fakes."""
    import websearch

    def _install(
        *,
        search_result: Any | Exception = None,
        fetch_result: Any | Exception = "page text",
    ):
        search_calls: list[dict[str, Any]] = []
        fetch_calls: list[dict[str, Any]] = []

        async def fake_search_web(**kwargs: Any) -> str:
            search_calls.append(kwargs)
            if isinstance(search_result, Exception):
                raise search_result
            if search_result is None:
                return json.dumps([])
            if isinstance(search_result, str):
                return search_result
            return json.dumps(search_result)

        async def fake_fetch_url(**kwargs: Any) -> str:
            fetch_calls.append(kwargs)
            if isinstance(fetch_result, Exception):
                raise fetch_result
            return str(fetch_result)

        monkeypatch.setattr(
            websearch,
            "_resolve_builtins",
            lambda: (fake_search_web, fake_fetch_url),
        )
        return search_calls, fetch_calls

    return _install
