from __future__ import annotations

import pytest

from websearch import _domain_of, _filter_results, _matches_any, _split_csv


def test_split_csv_trims_and_lowers() -> None:
    assert _split_csv(" Example.com , FOO.org ,, bar ") == ["example.com", "foo.org", "bar"]


def test_split_csv_empty() -> None:
    assert _split_csv("") == []


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.example.com/path", "www.example.com"),
        ("HTTP://EXAMPLE.COM", "example.com"),
        ("not a url", ""),
        ("", ""),
    ],
)
def test_domain_of(url: str, expected: str) -> None:
    assert _domain_of(url) == expected


def test_matches_any_handles_subdomains() -> None:
    assert _matches_any("docs.example.com", ["example.com"]) is True
    assert _matches_any("example.com", ["example.com"]) is True
    assert _matches_any("notexample.com", ["example.com"]) is False
    assert _matches_any("", ["example.com"]) is False


def test_filter_results_allow_only() -> None:
    results = [
        {"link": "https://a.example.com/1"},
        {"link": "https://b.other.org/2"},
    ]
    assert _filter_results(results, allow=["example.com"], block=[]) == [results[0]]


def test_filter_results_block_only() -> None:
    results = [
        {"link": "https://a.example.com/1"},
        {"link": "https://b.other.org/2"},
    ]
    assert _filter_results(results, allow=[], block=["example.com"]) == [results[1]]


def test_filter_results_allow_and_block() -> None:
    results = [
        {"link": "https://a.example.com/1"},
        {"link": "https://b.example.com/2"},
        {"link": "https://c.other.org/3"},
    ]
    out = _filter_results(results, allow=["example.com"], block=["b.example.com"])
    assert out == [results[0]]


def test_filter_results_no_filters_passthrough() -> None:
    results = [{"link": "https://x.test/1"}, {"link": "https://y.test/2"}]
    assert _filter_results(results, allow=[], block=[]) == results


def test_filter_results_drops_results_without_link_when_allow_set() -> None:
    results = [{"link": ""}, {"link": "https://example.com/x"}]
    assert _filter_results(results, allow=["example.com"], block=[]) == [results[1]]
