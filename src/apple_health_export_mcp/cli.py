"""Ingest CLI — build the SQLite DB from an Apple Health export.zip (ADR-0006).

Exposed as the `apple-health-export-mcp-ingest` console script (separate from the
server, which is the bare `apple-health-export-mcp` command — see server.main).
Run from PyPI/git with: `uvx --from apple-health-export-mcp apple-health-export-mcp-ingest <zip>`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .db import db_path
from .ingest import ingest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apple-health-export-mcp-ingest",
        description="Parse an Apple Health export.zip into SQLite.",
    )
    parser.add_argument("zip", type=Path, help="Path to the exported export.zip")
    parser.add_argument("--db", type=Path, default=None, help="DB path (default: $AH_DB_PATH or XDG).")
    args = parser.parse_args(argv)

    if not args.zip.expanduser().exists():
        print(f"error: no such file: {args.zip}", file=sys.stderr)
        return 1
    dest = args.db or db_path()
    print(f"Ingesting {args.zip} → {dest}")
    counts = ingest(args.zip, args.db)
    print(f"Done: {counts['record']:,} records, {counts['workout']:,} workouts → {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
