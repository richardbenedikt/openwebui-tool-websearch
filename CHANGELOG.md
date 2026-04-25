# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-25
### Added
- Initial release.
- `web_search` method that delegates to Open WebUI's built-in `search_web`.
- `fetch_url` method that delegates to Open WebUI's built-in `fetch_url`.
- Valves: `result_count`, `allow_domains`, `block_domains`, `enable_fetch_url`.
- Status events for searching and fetching.
- Pytest suite with Open WebUI built-ins fully mocked.
- Ruff + Black + pre-commit configuration.
- GitHub Actions CI (Python 3.11 and 3.12).

## [Unreleased]

### Added
- `auto_fetch_top` valve (default `2`, range 0–5). After every `web_search`, fetches the top N pages in parallel and embeds their text as a `content` field on each result. Pages that fail to fetch get a `fetch_error` field instead. This bypasses models that ignore `fetch_url` even when prompted, so answers are based on real page bodies.

### Changed
- Removed the `language` valve; the `lang:<code>` query suffix was non-standard and broke results on most engines. Engine-side language config should be used instead.
- `web_search` and `fetch_url` docstrings strengthened to push the model to read pages instead of stopping at snippets.
- `web_search` response now includes a `hint` field reminding the model to call `fetch_url` (or read pre-fetched `content`) before answering. Omitted when there are no results or `enable_fetch_url` is off.
