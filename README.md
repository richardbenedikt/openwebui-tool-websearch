# OpenWebUI Web Search Tool

[![CI](https://github.com/richardbenedikt/openwebui-tool-websearch/actions/workflows/ci.yml/badge.svg)](https://github.com/richardbenedikt/openwebui-tool-websearch/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A small [Open WebUI](https://github.com/open-webui/open-webui) tool that lets the model search the web and fetch pages **only when it actually needs to**. It queries DuckDuckGo directly over HTTPS - no Open WebUI search backend configuration required, no API keys.

## Features

- **Two-tool surface** the LLM understands: `web_search` (snippets) and `fetch_url` (full page text).
- **Native function calling** - the model decides whether and how often to call. Multiple, refining searches per inference are supported and explicitly encouraged in the docstrings.
- **Direct DuckDuckGo HTML scraping** - no API keys, no upstream search config required from your Open WebUI admin.
- **Domain allow/block lists** applied to both search results and `fetch_url` targets.
- **Polite rate limiting** (2 s default between requests) and **rotating realistic User-Agents** to stay below DDG's anti-bot thresholds.
- **Status events** for visible progress in the chat UI.
- **Per-URL citations** - every `web_search` emits a single bundled citation event whose `document` / `metadata` arrays carry one entry per result, so all result URLs appear as sub-sources under one search chip. Each `fetch_url` call emits its own citation with the full page body.
- **Single-file deployment** - copy `websearch.py` into Workspace → Tools.

## Requirements

- Open WebUI **0.6.0** or newer. No admin search-engine configuration required.
- Python **3.11+** for development.

## Installation

### Option A - Workspace upload (recommended)

1. Open Open WebUI → **Workspace → Tools → +**.
2. Paste the contents of [`websearch.py`](websearch.py) and save.
3. Enable the tool on a model that supports **Native** function calling.

### Option B - Import from URL

In Workspace → Tools → Import, paste the raw URL of `websearch.py` from your fork or this repo.

## Configuration (Valves)

| Valve | Type | Default | Effect |
|---|---|---|---|
| `result_count` | int (1–20) | `5` | Default number of results returned. The model may override per call (clamped to 1–20). |
| `allow_domains` | csv string | `""` | If set, only results from these domains (or subdomains) survive the filter. Also enforced on `fetch_url`. |
| `block_domains` | csv string | `""` | Drops results from these domains (or subdomains). Also enforced on `fetch_url`. |
| `enable_fetch_url` | bool | `true` | Master kill switch for the `fetch_url` method. |
| `safe_search` | `strict` / `moderate` / `off` | `moderate` | DuckDuckGo SafeSearch level (maps to the `kp` query parameter). |
| `min_request_interval_ms` | int (0–60000) | `2000` | Minimum milliseconds between outbound requests. Lower at your own risk - DuckDuckGo will rate-limit or captcha-block aggressive scrapers. |
| `debug_log_raw_on_parse_failure` | bool | `false` | When the search response is non-empty but yields zero parsed results, emit a status event with a truncated repr (≤1000 chars) of the raw HTML. Use this to diagnose DuckDuckGo markup changes. |

All values are configurable from **Workspace → Tools → Web Search → ⚙️**.

## How the model uses it

The first sentence of each tool's docstring is what the LLM sees and gates on. They are deliberately blunt:

- `web_search` - *"Search the web when the user's question requires current, recent, or post-training-cutoff information… After results come back, call fetch_url on one or more of the most relevant links to read the full page before answering - snippets are short and frequently misleading…"*
- `fetch_url` - *"Fetch the full text of a specific URL when web_search has returned candidate links. You should call this on at least one - usually two or three - of the top results before answering any non-trivial question…"*

This means: trivia, math, and well-known facts won't trigger a search; questions about current events or post-cutoff topics will trigger a search **and** typically one or more `fetch_url` calls. The search response also embeds a short `hint` field reminding the model to read pages before answering.

### Return shape

Both methods return a JSON-encoded string with a stable shape:

```json
{"results": [{"title": "...", "link": "...", "snippet": "..."}], "hint": "..."}
{"url": "https://...", "content": "page text"}
{"error": "human-readable reason"}
```

`web_search` returns only snippets - the model is expected to call `fetch_url` for any non-trivial answer. The `hint` is present on empty results (telling the model to retry with a broader query) and on non-empty results when `enable_fetch_url` is on (telling the model to read pages before answering). It is omitted on results when `enable_fetch_url` is off.

## Development

```bash
git clone https://github.com/richardbenedikt/openwebui-tool-websearch.git
cd openwebui-tool-websearch
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

ruff check .
black --check .
pytest -q
```

Tests mount an `httpx.MockTransport` on the tool instead of hitting the network, so they run anywhere - no Open WebUI install required.

## Limitations

- Uses DuckDuckGo's public HTML endpoint. DDG may rate-limit or captcha-block aggressive use; the tool defaults to 2 s between requests for this reason. If you see "DuckDuckGo declined the request" warnings in chat, raise `min_request_interval_ms`.
- `fetch_url` does not execute JavaScript; pages that render entirely client-side will return little useful text.
- Page bodies are truncated to 20 000 characters.
- DDG HTML markup can change. The `debug_log_raw_on_parse_failure` valve exists to surface unrecognized response shapes for diagnosis.

## Contributing

Issues and PRs welcome - see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup. For sensitive reports, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE).
