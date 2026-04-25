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
