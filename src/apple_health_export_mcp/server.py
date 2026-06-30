"""FastMCP server: data-access tools + registration of coaching prompts.

Tools are thin wrappers over `queries.py` (where the testable SQL lives) and return
aggregates only (ADR-0008). The DB must already exist — build it with
`apple-health-export-mcp ingest <export.zip>` (ADR-0006). Coaching prompts live in
`prompts.py` and are registered at the bottom.
"""

from __future__ import annotations

import os
import signal
from contextlib import contextmanager
from typing import Annotated, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

# Absolute imports: `fastmcp run` loads this file by path (no package parent), so
# relative imports would fail. The package is installed in the env, so these resolve.
from apple_health_export_mcp import prompts, queries
from apple_health_export_mcp.db import connect

mcp = FastMCP("apple-health")

# All tools only read a local, fixed DB: safe to retry, no side effects, no open world.
READONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}

# --- Reusable, self-documenting argument types (FastMCP Field metadata) ------
TypeId = Annotated[
    str,
    Field(
        description="HealthKit type identifier. Discover valid values with `list_types`.",
        examples=["HKQuantityTypeIdentifierStepCount", "HKQuantityTypeIdentifierRestingHeartRate"],
    ),
]
DateStr = Annotated[
    str,
    Field(
        description="Local calendar date, ISO 'YYYY-MM-DD'.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        examples=["2026-06-30"],
    ),
]
Agg = Annotated[
    Literal["sum", "avg", "min", "max", "count"],
    Field(
        description="Aggregation: 'sum' for cumulative metrics (steps, energy), "
        "'avg' for sampled ones (heart rate, weight)."
    ),
]
Bucket = Annotated[
    Literal["day", "week", "month", "all"],
    Field(description="Group results by this time bucket."),
]
Source = Annotated[
    str | None,
    Field(description="Restrict to one source/device (see `list_sources`). Omit to auto-dedupe parallel devices."),
]


@contextmanager
def _store():
    """Open the health DB for the duration of one tool call.

    Surfaces a clean ToolError (instead of a raw traceback) when the DB hasn't
    been built yet, and always closes the connection.
    """
    try:
        conn = connect(create=False)
    except FileNotFoundError as e:
        raise ToolError(str(e)) from e
    try:
        yield conn
    finally:
        conn.close()


@mcp.tool(annotations=READONLY)
def list_types() -> list[queries.TypeInfo]:
    """List which health metrics exist in this export, with row counts and date spans.

    Call this first to discover the exact `type` strings to pass to `get_quantity`.
    """
    with _store() as conn:
        return queries.list_types(conn)


@mcp.tool(annotations=READONLY)
def list_sources(type: TypeId) -> list[queries.SourceInfo]:
    """List which sources/devices wrote a metric, with counts and date spans.

    Use it to see why a `sum` differs across devices, or to pick a `source` for `get_quantity`.
    """
    with _store() as conn:
        return queries.list_sources(conn, type)


@mcp.tool(annotations=READONLY)
def get_quantity(
    type: TypeId,
    start: DateStr,
    end: DateStr,
    agg: Agg = "sum",
    bucket: Bucket = "day",
    source: Source = None,
) -> list[queries.QuantityPoint]:
    """Aggregate a numeric metric (steps, weight, heart rate, energy…) over a date range.

    Call `list_types` first to find the exact `type` string. Pick `agg` by metric kind:
    `sum` for cumulative (steps, active energy), `avg` for sampled (weight, heart rate).
    `sum` auto-deduplicates parallel devices (Watch + iPhone + apps) per day, so it does
    not over-count (ADR-0010); pass `source` to force one device. `avg/min/max` are not
    deduped. Returns [{period, value, n}].
    """
    with _store() as conn:
        try:
            return queries.quantity(conn, type, start, end, agg, bucket, source)
        except ValueError as e:
            raise ToolError(str(e)) from e


@mcp.tool(annotations=READONLY)
def get_sleep(start: DateStr, end: DateStr) -> list[queries.SleepNight]:
    """Per-night sleep stage durations (minutes), attributed to the wake-up day.

    Returns [{night, asleep_min, rem_min, deep_min, core_min, awake_min, in_bed_min}].
    Older nights may report only in_bed_min (legacy devices lack stage detail).
    """
    with _store() as conn:
        return queries.sleep(conn, start, end)


@mcp.tool(annotations=READONLY)
def get_workouts(start: DateStr, end: DateStr) -> list[queries.WorkoutSummary]:
    """Workout summary per activity type in a date range: count, total & avg minutes."""
    with _store() as conn:
        return queries.workouts(conn, start, end)


# Register coaching prompts (defined in prompts.py).
for _prompt in prompts.ALL:
    mcp.prompt(_prompt)


def main() -> None:
    """Console-script entry point: run the stdio MCP server.

    This is the *bare* `apple-health-export-mcp` command (Pattern B), so clients
    launch it as `uvx apple-health-export-mcp` — matching every reference MCP
    server and keeping the process tree shallow. The stdio transport exits on
    stdin EOF, which is the MCP spec's primary shutdown signal and the reliable
    defense against orphaned processes (signal forwarding through wrappers like
    uv is unreliable). For zero wrapper layers, install once with
    `uv tool install` and point the client at the installed binary directly.
    """
    # Exit immediately on Ctrl+C. The stdio transport runs a blocking stdin-reader
    # thread that asyncio can't cancel, so the default SIGINT path hangs (and prints
    # a traceback). Our own handler sidesteps it. Clients shut down via stdin EOF
    # (clean return below), so this only affects interactive runs.
    # ponytail: nothing to flush — DB connections are per-call — so a hard exit is safe.
    signal.signal(signal.SIGINT, lambda *_: os._exit(0))
    mcp.run()


if __name__ == "__main__":
    main()
