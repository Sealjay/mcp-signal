# mcp-signal

Minimal Signal MCP server: read and search Signal Desktop data locally via `signal-export`, then send outbound messages via `signal-cli` JSON-RPC. stdio by default; `serve --http` is stateless streamable HTTP (MCP 2026-07-28 and older).

## Commands

```bash
uv sync
uv run signal-mcp smoke
uv run pytest
uv run ruff check .
```

## Structure

```text
src/mcp_signal/
  config.py       Environment parsing and defaults
  reader.py       Signal Desktop read/search via sigexport
  signal_cli.py   signal-cli JSON-RPC wrapper for send + group resolution
  link_manager.py signal-cli device-linking + QR URI capture
  server.py       FastMCP tool registration
  main.py         CLI entry point (serve / smoke), HTTP auth + /health
tests/
```

## Constraints

- British English for prose, American English in code.
- Pin Python dependencies exactly.
- Keep the tool surface small: read/search/send plus the setup helpers.
- Prefer clear tool errors over silent fallbacks.

