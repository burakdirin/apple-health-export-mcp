# Contributing

Thanks for your interest! This is a small, focused project — keep changes minimal
and well-tested.

## Setup

```bash
uv sync
```

## Before opening a PR

```bash
uv run ruff format     # format
uv run ruff check      # lint
uv run pytest          # tests
```

All three run in CI on Python 3.11–3.13.

## Guidelines

- Query logic lives in `queries.py` (pure, unit-tested); `server.py` only wraps it
  as MCP tools. Keep that split.
- Non-trivial logic ships with a test.
- Architecture decisions are recorded in [`docs/adr.md`](docs/adr.md) — add an entry
  for anything that changes how data is parsed, stored, or aggregated.
- Never commit personal health data (`*.zip` / `*.db` are git-ignored).
