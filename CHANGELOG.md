# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-06-30

### Changed
- Tools now return typed dataclass models instead of bare dicts, so each tool
  publishes a JSON **output schema** (`structuredContent` is unchanged). Clients
  can validate fields and see the shape up front.
- Internal: extracted the tool surface into `tools.py` (mirrors `prompts.py`), so
  `server.py` is wiring only. No behavior change.

## [0.1.0]

### Added
- Streaming ingest of an Apple Health `export.zip` into SQLite (`apple-health-export-mcp ingest`),
  locale-independent (finds the main XML by content, not filename).
- Idempotent, content-hash de-duplication on re-ingest.
- Two console scripts: `apple-health-export-mcp` (bare command runs the stdio MCP
  server) and `apple-health-export-mcp-ingest` (build the DB). The server shuts down
  on stdin EOF and is meant to be launched directly (no wrapper) to avoid orphaned
  processes — see README "Shutdown & process model".
- MCP tools: `list_types`, `list_sources`, `get_quantity`, `get_sleep`, `get_workouts`
  (aggregates only; configurable date range).
- Per-day dominant-source de-duplication for `sum` aggregation, mirroring Apple's
  multi-source merge so totals aren't inflated.
- Coaching prompts: `daily_summary`, `weekly_review`, `monthly_summary`,
  `yearly_summary`, `readiness_check`, `sleep_report`.

[Unreleased]: https://github.com/burakdirin/apple-health-export-mcp/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/burakdirin/apple-health-export-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/burakdirin/apple-health-export-mcp/releases/tag/v0.1.0
