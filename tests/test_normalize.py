from __future__ import annotations

import json

from websearch import _looks_empty, _normalize


def test_normalize_json_string_list() -> None:
    raw = json.dumps([{"title": "T", "link": "https://x", "snippet": "S"}])
    assert _normalize(raw) == [{"title": "T", "link": "https://x", "snippet": "S"}]


def test_normalize_dict_with_results_key() -> None:
    raw = json.dumps({"results": [{"title": "T", "link": "https://x", "snippet": "S"}]})
    assert _normalize(raw) == [{"title": "T", "link": "https://x", "snippet": "S"}]


def test_normalize_already_parsed_list() -> None:
    raw = [{"title": "T", "link": "https://x", "snippet": "S"}]
    assert _normalize(raw) == raw


def test_normalize_alternate_keys() -> None:
    raw = [{"title": "T", "url": "https://x", "content": "C"}]
    assert _normalize(raw) == [{"title": "T", "link": "https://x", "snippet": "C"}]


def test_normalize_missing_keys_default_to_empty() -> None:
    raw = [{}]
    assert _normalize(raw) == [{"title": "", "link": "", "snippet": ""}]


def test_normalize_malformed_json_returns_empty() -> None:
    assert _normalize("not json") == []


def test_normalize_none_returns_empty() -> None:
    assert _normalize(None) == []


def test_normalize_drops_non_dict_entries() -> None:
    assert _normalize(["string", 42, {"title": "T"}]) == [{"title": "T", "link": "", "snippet": ""}]


def test_looks_empty_recognizes_known_empty_shapes() -> None:
    assert _looks_empty(None)
    assert _looks_empty("")
    assert _looks_empty("   ")
    assert _looks_empty([])
    assert _looks_empty({})
    assert _looks_empty({"results": []})
    assert _looks_empty("[]")
    assert _looks_empty("{}")
    assert _looks_empty('{"results": []}')


def test_looks_empty_flags_unrecognized_or_non_empty_shapes() -> None:
    assert not _looks_empty({"data": [{"title": "x"}]})
    assert not _looks_empty({"web": {"results": []}})
    assert not _looks_empty('{"data":[{"title":"x"}]}')
    assert not _looks_empty([{"title": "x"}])
    assert not _looks_empty("not json")
    assert not _looks_empty(42)
