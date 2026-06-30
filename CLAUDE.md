# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastMCP (v3) stdio MCP server that answers questions about a user's **exported** Apple Health archive. Apple has no live API, so the flow is two-stage and snapshot-based:

```
export.zip ──(ingest CLI, one-time)──► SQLite (health.db) ──◄── MCP server tools query it
```

The design rationale lives in [`docs/adr.md`](docs/adr.md) (10 ADRs). **Read it before changing how data is parsed, stored, or aggregated, and add an ADR entry for such changes** — the reasoning there is load-bearing and not re-derivable from the diff.

## Commands

```bash
uv sync                                   # set up the env
uv run pytest                             # all tests
uv run pytest tests/test_queries.py::test_sum_dedupes_parallel_sources_by_dominant_per_day  # single test
uv run ruff check                         # lint (CI gate)
uv run ruff format                        # format (CI checks --check)
uv run fastmcp inspect                    # list registered tools/prompts without a client
uv build                                  # sdist+wheel; uvx twine check dist/* before publishing

# Run the pieces directly:
apple-health-export-mcp-ingest <export.zip>   # build the DB (AH_DB_PATH or --db controls location)
apple-health-export-mcp                        # run the stdio server (reads the DB)
```

## Architecture

Layering is deliberate — keep it:

- **`queries.py`** — pure SQL helpers, **no FastMCP import**. This is where all query logic and the unit tests live. Anything non-trivial goes here so it stays testable without a server.
- **`server.py`** — thin FastMCP wrappers over `queries.py` (the `@mcp.tool` functions) plus prompt registration. Tools open the DB via the `_store()` context manager and translate `ValueError`/missing-DB into `ToolError`. Reusable `Annotated[..., Field(...)]` argument types are defined at the top.
- **`prompts.py`** — coaching prompt **content** as plain (un-decorated) functions exported via `ALL`; `server.py` registers them with `mcp.prompt(fn)`. Kept decorator-free to avoid importing the `mcp` instance (no circular import).
- **`ingest.py`** — streaming `iterparse` of the export XML into SQLite; the one-time builder.
- **`db.py`** — schema + `connect()` + `db_path()` (env/XDG resolution).
- **`cli.py`** — the `apple-health-export-mcp-ingest` entry point.

Two console scripts (see `[project.scripts]`): the **bare** `apple-health-export-mcp` runs the server (`server:main`), `-ingest` runs the CLI. This Pattern-B split is intentional (matches reference MCP servers; shallow process tree).

## Non-obvious invariants (these will bite you)

- **`server.py` uses absolute imports** (`from apple_health_export_mcp import ...`), not relative. `fastmcp run` loads the file by path with no package parent, so relative imports break there.
- **Generic schema, `type` is a string column.** New HealthKit types need no code. `record.value` is **TEXT** (quantity types are numeric, category types are string enums like `…AsleepDeep`); numeric SQL must `CAST(value AS REAL)`.
- **Local day = `substr(start, 1, 10)`.** Apple writes timestamps in local time with the offset appended (`2026-06-29 08:14:22 +0300`), stored verbatim — no timezone conversion needed or wanted (ADR-0009).
- **`get_quantity` `sum` de-duplicates by per-day dominant source** (most records that day) to avoid double-counting parallel devices (Watch + iPhone + apps); `avg/min/max/count` are left raw. The known ceiling (mid-day device switch can under-count) and the upgrade path are in ADR-0010.
- **The main export XML is found by content, not filename** — a localized export names it e.g. `dışa aktarılan.xml`, not `export.xml`. Type identifiers and sleep enums stay English regardless of `locale`.
- **Tools return aggregates only** (ADR-0008) — never raw rows; a metric can hold millions of samples.
- **Shutdown:** the server exits on stdin EOF (the MCP spec's primary mechanism) and installs a SIGINT handler that `os._exit(0)`s to avoid hanging on the blocking stdin-reader thread. Launch it with as few wrapper layers as possible (`uv`/`uvx` only conditionally forward signals → orphan risk). Never reintroduce `fastmcp run fastmcp.json` as the client-facing command.

## Paths & config

No hard-coded paths. The zip is a CLI argument; the DB path comes from `AH_DB_PATH` (else XDG default `~/.local/share/apple-health-export-mcp/health.db`). `.gitignore` excludes `*.zip`/`*.db` so health data never enters git.

## Release

Version is single-sourced from `src/apple_health_export_mcp/__init__.py` (`[tool.hatch.version]`). To release: bump `__version__`, update `CHANGELOG.md`, then `gh release create vX.Y.Z` — `.github/workflows/publish.yml` publishes to PyPI via Trusted Publishing (OIDC, no token). CI (`ci.yml`) runs ruff + pytest on 3.11–3.13.
