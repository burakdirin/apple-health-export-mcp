"""FastMCP server: wires the tool and prompt surfaces onto a stdio server.

The tool surface lives in `tools.py`, coaching prompts in `prompts.py`, and the
query logic in `queries.py`. This module only creates the server, registers those
surfaces, and runs it.
"""

from __future__ import annotations

import os
import signal

from fastmcp import FastMCP

# Absolute imports: `fastmcp run` loads this file by path (no package parent), so
# relative imports would fail. The package is installed in the env, so these resolve.
from apple_health_export_mcp import prompts, tools

mcp = FastMCP("apple-health")

for _tool in tools.ALL:
    mcp.tool(annotations=tools.READONLY)(_tool)
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
