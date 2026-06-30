# apple-health-export-mcp

[![CI](https://github.com/burakdirin/apple-health-export-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/burakdirin/apple-health-export-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/apple-health-export-mcp.svg)](https://pypi.org/project/apple-health-export-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/apple-health-export-mcp.svg)](https://pypi.org/project/apple-health-export-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant query your **Apple Health** data — sleep, heart rate, steps, body mass, workouts, and any other metric in your export.

Apple has no live export API, so this works on a **snapshot**: you export your health archive once, ingest it into a local SQLite database, then the server answers queries against it. See [`docs/adr.md`](docs/adr.md) for why.

> **Privacy:** your health data never leaves your machine and is never committed to git (`.gitignore` excludes `*.zip` / `*.db`).

## How it works

```
export.zip ──(ingest, one-time ~1-3 min)──► health.db (SQLite) ──◄── MCP server queries
```

## Setup

1. **Export your data** on iPhone: _Settings → Health → tap your photo → Export All Health Data_. AirDrop/save the resulting `export.zip`.

2. **Install** with [uv](https://docs.astral.sh/uv/). Installing once (rather than
   `uvx` on every launch) keeps the process tree shallow, which matters for clean
   shutdown — see [Shutdown & process model](#shutdown--process-model).

   ```bash
   uv tool install apple-health-export-mcp
   # …or before it's on PyPI, from GitHub:
   uv tool install git+https://github.com/burakdirin/apple-health-export-mcp
   ```

   This puts two commands on your PATH: `apple-health-export-mcp` (the server) and
   `apple-health-export-mcp-ingest`.

3. **Ingest** the archive (one time per new export):

   ```bash
   AH_DB_PATH=~/.local/share/apple-health-export-mcp/health.db \
     apple-health-export-mcp-ingest ~/Downloads/export.zip
   ```

4. **Add to your MCP client** (e.g. Claude Code `.mcp.json`). The bare command
   starts the stdio server; point it at the DB you just built.

   **Installed (recommended)** — invoke the binary directly (no wrapper process):

   ```json
   {
     "mcpServers": {
       "apple-health": {
         "command": "apple-health-export-mcp",
         "env": { "AH_DB_PATH": "/Users/you/.local/share/apple-health-export-mcp/health.db" }
       }
     }
   }
   ```

   Use an absolute path to the binary (`which apple-health-export-mcp`) if your
   client doesn't inherit your `PATH`.

   **Or via `uvx`** (no install; the bare package name runs the server):

   ```json
   {
     "mcpServers": {
       "apple-health": {
         "command": "uvx",
         "args": ["apple-health-export-mcp"],
         "env": { "AH_DB_PATH": "/Users/you/.local/share/apple-health-export-mcp/health.db" }
       }
     }
   }
   ```

   `claude mcp add` equivalent:

   ```bash
   claude mcp add apple-health --env AH_DB_PATH=~/.local/share/apple-health-export-mcp/health.db \
     -- apple-health-export-mcp
   ```

## Shutdown & process model

The server is a single process that shuts down on **stdin EOF** — the MCP
spec's primary shutdown signal — so closing your client terminates it cleanly.
Avoid extra wrapper layers (`uv run … fastmcp run …`): `uv`/`uvx` stay in the
process tree as a parent and only *conditionally* forward signals, so a wrapped
server can be orphaned when the client exits or you press Ctrl+C. Installing the
tool and launching the binary directly (config above) gives the shallowest tree
and the most reliable cleanup. `fastmcp run fastmcp.json` is for local dev only.

## Tools

| Tool                                          | Returns                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| `list_types()`                                | Which metrics exist in _your_ data + row counts (discovery)              |
| `get_quantity(type, start, end, agg, bucket)` | Daily/weekly aggregate for a numeric metric (steps, heart rate, weight…) |
| `get_sleep(start, end)`                       | Per-night sleep stage durations                                          |
| `get_workouts(start, end)`                    | Workouts in the range                                                    |

All query tools require a date range and return **aggregates only** — never raw rows (ADR-0008).
`get_quantity` with `agg="sum"` auto-deduplicates parallel devices (Watch + iPhone + apps) so totals aren't inflated (ADR-0010); pass `source` to force one device.

## Prompts

Reusable coaching workflows the client can invoke (they orchestrate the tools and reply in your language):

| Prompt                       | Purpose                                            |
| ---------------------------- | -------------------------------------------------- |
| `daily_summary(day?)`        | One day's snapshot                                 |
| `weekly_review(week_of?)`    | Calendar week (Mon–Sun): load vs recovery + advice |
| `monthly_summary(month?)`    | A month in review (YYYY-MM)                        |
| `yearly_summary(year?)`      | A year's fitness trajectory (YYYY)                 |
| `readiness_check()`          | Train hard today? From sleep + recovery markers    |
| `sleep_report(start?, end?)` | Sleep duration, stages, consistency                |

Arguments are optional — they default to today / this week / this month / this year.

## Development

```bash
uv sync
uv run pytest
uv run ruff check
```

## License

MIT
