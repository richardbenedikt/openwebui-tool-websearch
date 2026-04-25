# Contributing

Issues and PRs welcome. Keep changes scoped — this is a single-file tool.

## Dev setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Run the checks

```bash
ruff check .
black --check .
pytest -q
```

The same three commands run in CI on Python 3.11 and 3.12.

## Notes

- PEP 8, line length 120. Ruff and Black are the source of truth.
- Type hints on public symbols.
- `websearch.py` must stay self-contained — Open WebUI loads it as a single uploaded blob, so sibling modules are not importable at runtime.
- Bump `version:` in the `websearch.py` frontmatter (and `pyproject.toml`) when behavior changes.
