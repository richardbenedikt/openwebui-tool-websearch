# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-05-03
### Added
- `debug_log_raw_on_parse_failure` valve (default `false`). When the search backend returns an unrecognized response shape, also emits a status event with a truncated repr (≤1000 chars) of the raw payload. Use this to diagnose parse failures from DuckDuckGo or other backends whose response shape `_normalize` does not recognize.

## [2.2.0] - 2026-04-26
### Added
- `web_search` now returns a retry hint on empty results, instructing the model to broaden/simplify the query before declining to answer. Closes the failure mode where the model interpreted "0 results" as "I cannot search" and gave up.
- Diagnostic warning event when the search backend returns an unrecognized response shape (previously silently coerced to `[]`).
### Changed
- `web_search` docstring strengthened with explicit guidance on retrying after empty results.

## [2.1.0] - 2026-04-26
### Added
- Per-URL citation events for every page that gets fetched (both via auto-fetch and explicit `fetch_url`). Open WebUI now displays each fetched page as its own clickable source in the chat instead of a single generic `websearch/web_search` entry.

## [2.0.0] - 2026-04-26
### Added
- `auto_fetch_enabled` valve (default `true`). Dedicated master switch for the post-search auto-fetch step; when `false`, `web_search` returns snippets only but the model can still call `fetch_url` itself.
### Changed
- **Breaking:** `auto_fetch_top` semantics changed. `0` is now the default and means "fetch every returned result" (previously `0` disabled pre-fetching). The upper bound was raised from `10` to `20` to match `result_count`. Migration: to skip pre-fetching while keeping `fetch_url` available to the model, set `auto_fetch_enabled=false` (preserves the previous "0 disables" behavior).

## [1.1.0] - 2026-04-25
### Added
- `auto_fetch_top` valve (default `2`, range 0–5). After every `web_search`, fetches the top N pages in parallel and embeds their text as a `content` field on each result. Pages that fail to fetch get a `fetch_error` field instead. This bypasses models that ignore `fetch_url` even when prompted, so answers are based on real page bodies.
### Changed
- Removed the `language` valve; the `lang:<code>` query suffix was non-standard and broke results on most engines. Engine-side language config should be used instead.
- `web_search` and `fetch_url` docstrings strengthened to push the model to read pages instead of stopping at snippets.
- `web_search` response now includes a `hint` field reminding the model to call `fetch_url` (or read pre-fetched `content`) before answering. Omitted when there are no results or `enable_fetch_url` is off.

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
