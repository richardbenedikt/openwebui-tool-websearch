# OpenWebUI Web Search Tool

[![CI](https://github.com/richardbenedikt/openwebui-websearch-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/richardbenedikt/openwebui-websearch-tool/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A small, well-behaved [Open WebUI](https://github.com/open-webui/open-webui) tool that lets the model search the web and fetch pages **only when it actually needs to**. It is a thin adapter over OpenWebUI's built-in `search_web` / `fetch_url`, so it inherits whatever search engine you have already configured (DuckDuckGo, Brave, Google PSE, Tavily, …) — no extra API keys required.

> _Screenshot/GIF placeholder — drop a recording of the tool firing in a chat here once published._

## Features

- **Two-tool surface** the LLM understands: `web_search` (snippets) and `fetch_url` (full page text).
- **Native function calling** — the model decides whether and how often to call. Multiple, refining searches per inference are supported and explicitly encouraged in the docstrings.
- **Reuses your OpenWebUI search backend** — no duplicate engine config, no extra keys.
- **Domain allow/block lists** applied to both search results and `fetch_url` targets.
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
| `enable_fetch_url` | bool | `true` | Master kill switch for the `fetch_url` method. |

All values are configurable from **Workspace → Tools → Web Search → ⚙️**.

## How the model uses it

The first sentence of each tool's docstring is what the LLM sees and gates on. They are deliberately blunt:

- `web_search` — *"Search the web when the user's question requires current, recent, or post-training-cutoff information, or specific facts you do not reliably know. Call multiple times with refined queries if the first results are insufficient. Do not call for general knowledge, math, or topics fully covered by your training data."*
- `fetch_url` — *"Fetch the full text of a specific URL when a snippet from web_search is not enough… Do not call without first having a URL from web_search results or directly from the user."*

This means: trivia, math, and well-known facts won't trigger a search; questions about current events or post-cutoff topics will, and the model is free to refine and re-query.

### Return shape

Both methods return a JSON-encoded string with a stable shape:

```json
{"results": [{"title": "...", "link": "...", "snippet": "..."}]}
{"url": "https://...", "content": "page text"}
{"error": "human-readable reason"}
```

## Development

```bash
git clone https://github.com/richardbenedikt/openwebui-websearch-tool.git
cd openwebui-websearch-tool
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
