# OpenWebUI Web Search Tool

[![CI](https://github.com/richardbenedikt/openwebui-tool-websearch/actions/workflows/ci.yml/badge.svg)](https://github.com/richardbenedikt/openwebui-tool-websearch/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A small [Open WebUI](https://github.com/open-webui/open-webui) tool that lets the model search the web and fetch pages **only when it actually needs to**. It is a thin adapter over OpenWebUI's built-in `search_web` / `fetch_url`, so it inherits whatever search engine you have already configured (DuckDuckGo, Brave, Google PSE, Tavily, …) — no extra API keys required.

## Features

- **Two-tool surface** the LLM understands: `web_search` (snippets) and `fetch_url` (full page text).
- **Native function calling** — the model decides whether and how often to call. Multiple, refining searches per inference are supported and explicitly encouraged in the docstrings.
- **Reuses your OpenWebUI search backend** — no duplicate engine config, no extra keys.
- **Domain allow/block lists** applied to both search results and `fetch_url` targets.
- **Auto-fetches every result page by default** in parallel after every search, so answers are based on real page bodies rather than short snippets — even if the model wouldn't have called `fetch_url` itself. Configurable to a top-N cap.
- **Status events** for visible progress in the chat UI.
- **Single-file deployment** — copy `websearch.py` into Workspace → Tools.

## Requirements

- Open WebUI **0.6.0** or newer (with built-in `search_web` and `fetch_url` available).
- A search engine configured under **Admin → Settings → Web Search**.
- Python **3.11+** for development.

## Installation

### Option A — Workspace upload (recommended)

1. Open Open WebUI → **Workspace → Tools → +**.
2. Paste the contents of [`websearch.py`](websearch.py) and save.
3. Enable the tool on a model that supports **Native** function calling.
4. Make sure **Web Search** is enabled in admin settings.

### Option B — Import from URL

In Workspace → Tools → Import, paste the raw URL of `websearch.py` from your fork or this repo.

## Configuration (Valves)

| Valve | Type | Default | Effect |
|---|---|---|---|
| `result_count` | int (1–20) | `5` | Default number of results returned. The model may override per call (clamped to 1–20). |
| `allow_domains` | csv string | `""` | If set, only results from these domains (or subdomains) survive the filter. Also enforced on `fetch_url`. |
| `block_domains` | csv string | `""` | Drops results from these domains (or subdomains). Also enforced on `fetch_url`. |
| `enable_fetch_url` | bool | `true` | Master kill switch for the `fetch_url` method. Disabling also disables auto-fetch. |
| `auto_fetch_enabled` | bool | `true` | Master switch for the post-search auto-fetch step. When `false`, `web_search` returns snippets only, but the model can still call `fetch_url` itself. |
| `auto_fetch_top` | int (0–20) | `0` | When `auto_fetch_enabled` is on, controls how many pages are pre-fetched per search. `0` (default) fetches every returned result; a positive `N` caps pre-fetching to the top `N` (capped at the number of returned results). |

All values are configurable from **Workspace → Tools → Web Search → ⚙️**.

## How the model uses it

The first sentence of each tool's docstring is what the LLM sees and gates on. They are deliberately blunt:

- `web_search` — *"Search the web when the user's question requires current, recent, or post-training-cutoff information… After results come back, call fetch_url on one or more of the most relevant links to read the full page before answering — snippets are short and frequently misleading…"*
- `fetch_url` — *"Fetch the full text of a specific URL when web_search has returned candidate links. You should call this on at least one — usually two or three — of the top results before answering any non-trivial question…"*

This means: trivia, math, and well-known facts won't trigger a search; questions about current events or post-cutoff topics will trigger a search **and** typically one or more `fetch_url` calls. The search response also embeds a short `hint` field reminding the model to read pages before answering.

### Return shape

Both methods return a JSON-encoded string with a stable shape:

```json
{"results": [{"title": "...", "link": "...", "snippet": "...", "content": "full page text"}], "hint": "..."}
{"url": "https://...", "content": "page text"}
{"error": "human-readable reason"}
```

`content` is present on every returned result by default (`auto_fetch_top=0`) when both `enable_fetch_url` and `auto_fetch_enabled` are on; set a positive `N` to cap pre-fetching to the top `N`, or set `auto_fetch_enabled=false` to skip pre-fetching entirely while keeping `fetch_url` available to the model. On a fetch failure the entry gets `"fetch_error": "..."` instead. The `hint` is omitted when there are no results or when `enable_fetch_url` is off.

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

Tests stub out the OpenWebUI built-ins, so they run anywhere — no Open WebUI install required.

## Limitations

- Honors whatever search engine your OpenWebUI admin selected. If results are poor, fix it in Open WebUI's settings, not here.
- `fetch_url` does not execute JavaScript; pages that render entirely client-side will return little useful text.
- Page bodies are truncated by Open WebUI's `WEB_FETCH_MAX_CONTENT_LENGTH`.
- Couples to Open WebUI's internal `tools.builtin` module. If a future Open WebUI release moves it, the tool will fail with a clear `RuntimeError` and bump the minimum version requirement.

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup. For sensitive reports, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE).
