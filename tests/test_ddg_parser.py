from __future__ import annotations

from urllib.parse import quote

from websearch import _decode_ddg_redirect, _parse_ddg_html, _strip_html


def _ddg_result_html(title: str, href: str, snippet: str) -> str:
    return (
        f'<div class="result results_links">'
        f'  <h2 class="result__title">'
        f'    <a class="result__a" href="{href}">{title}</a>'
        f"  </h2>"
        f'  <a class="result__snippet">{snippet}</a>'
        f"</div>"
    )


def _wrap(uddg: str) -> str:
    return f"//duckduckgo.com/l/?uddg={quote(uddg, safe='')}&rut=abc"


def test_parse_ddg_html_basic_results() -> None:
    page = (
        "<html><body>"
        + _ddg_result_html("Example One", _wrap("https://example.com/a"), "First snippet.")
        + _ddg_result_html("Example Two", _wrap("https://example.org/b"), "Second snippet.")
        + "</body></html>"
    )
    results = _parse_ddg_html(page)
    assert results == [
        {"title": "Example One", "link": "https://example.com/a", "snippet": "First snippet."},
        {"title": "Example Two", "link": "https://example.org/b", "snippet": "Second snippet."},
    ]


def test_parse_ddg_html_decodes_uddg_redirect() -> None:
    page = _ddg_result_html("Title", _wrap("https://example.com/page?x=1"), "snip")
    results = _parse_ddg_html(page)
    assert results[0]["link"] == "https://example.com/page?x=1"


def test_parse_ddg_html_accepts_absolute_uddg_wrapper() -> None:
    href = f"https://duckduckgo.com/l/?uddg={quote('https://example.com/abs', safe='')}"
    page = _ddg_result_html("Title", href, "snip")
    results = _parse_ddg_html(page)
    assert results[0]["link"] == "https://example.com/abs"


def test_parse_ddg_html_drops_duckduckgo_internal_anchors() -> None:
    page = (
        "<html><body>"
        '<a class="result__a" href="/settings">Settings</a>'
        '<a class="result__a" href="https://duckduckgo.com/about">About</a>'
        + _ddg_result_html("Real Result", _wrap("https://example.com/x"), "snip")
        + "</body></html>"
    )
    results = _parse_ddg_html(page)
    assert [r["link"] for r in results] == ["https://example.com/x"]


def test_parse_ddg_html_dedupes_by_url() -> None:
    page = (
        "<html><body>"
        + _ddg_result_html("Duplicate A", _wrap("https://example.com/dup"), "first")
        + _ddg_result_html("Duplicate B", _wrap("https://example.com/dup"), "second")
        + "</body></html>"
    )
    results = _parse_ddg_html(page)
    assert len(results) == 1
    assert results[0]["title"] == "Duplicate A"


def test_parse_ddg_html_empty_input() -> None:
    assert _parse_ddg_html("") == []


def test_parse_ddg_html_no_result_class_returns_empty() -> None:
    page = "<html><body><p>No results for your query.</p></body></html>"
    assert _parse_ddg_html(page) == []


def test_parse_ddg_html_decodes_html_entities_in_title() -> None:
    page = _ddg_result_html("Foo &amp; Bar &#x27;quoted&#x27;", _wrap("https://example.com/e"), "x")
    results = _parse_ddg_html(page)
    assert results[0]["title"] == "Foo & Bar 'quoted'"


def test_parse_ddg_html_skips_nav_label_titles() -> None:
    href = _wrap("https://example.com/page")
    page = _ddg_result_html("Next", href, "snip")
    assert _parse_ddg_html(page) == []


def test_decode_ddg_redirect_passthrough_absolute() -> None:
    assert _decode_ddg_redirect("https://example.com/page") == "https://example.com/page"


def test_decode_ddg_redirect_rejects_javascript_scheme() -> None:
    assert _decode_ddg_redirect("javascript:alert(1)") is None


def test_decode_ddg_redirect_rejects_internal_duckduckgo_paths() -> None:
    assert _decode_ddg_redirect("https://duckduckgo.com/settings") is None
    assert _decode_ddg_redirect("//duckduckgo.com/about") is None


def test_decode_ddg_redirect_handles_protocol_relative_wrapper() -> None:
    href = f"//duckduckgo.com/l/?uddg={quote('https://example.com/y', safe='')}"
    assert _decode_ddg_redirect(href) == "https://example.com/y"


def test_decode_ddg_redirect_returns_none_for_empty() -> None:
    assert _decode_ddg_redirect("") is None


def test_decode_ddg_redirect_returns_none_for_non_http_uddg() -> None:
    href = f"//duckduckgo.com/l/?uddg={quote('javascript:alert(1)', safe='')}"
    assert _decode_ddg_redirect(href) is None


def test_strip_html_drops_script_and_style() -> None:
    page = "<html><head><style>body{color:red}</style></head><body><script>x=1</script>Hello</body></html>"
    assert _strip_html(page) == "Hello"


def test_strip_html_collapses_whitespace_and_inserts_block_breaks() -> None:
    page = "<p>Hello</p><p>World</p>"
    assert _strip_html(page) == "Hello World"


def test_strip_html_decodes_entities() -> None:
    assert _strip_html("<p>Foo &amp; bar</p>") == "Foo & bar"


def test_strip_html_handles_empty() -> None:
    assert _strip_html("") == ""


def test_strip_html_drops_svg_content() -> None:
    page = "<p>Before<svg><circle/>noise</svg>After</p>"
    assert _strip_html(page) == "Before After"
