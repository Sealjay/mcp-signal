# mcp-signal

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=ffffff)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-package%20manager-4B5563)](https://docs.astral.sh/uv/)
[![MCP](https://img.shields.io/badge/MCP-Model_Context_Protocol-6E44FF)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/github/license/Sealjay/mcp-signal)](LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/Sealjay/mcp-signal)](https://github.com/Sealjay/mcp-signal/issues)
[![GitHub stars](https://img.shields.io/github/stars/Sealjay/mcp-signal?style=social)](https://github.com/Sealjay/mcp-signal)
[![Sealjay/mcp-signal MCP server](https://glama.ai/mcp/servers/Sealjay/mcp-signal/badges/score.svg)](https://glama.ai/mcp/servers/Sealjay/mcp-signal)

A local MCP server for Signal. It reads and searches your Signal Desktop history via [`signal-export`](https://github.com/carderne/signal-export) and sends messages via [`signal-cli`](https://github.com/AsamK/signal-cli). Everything runs on your machine over stdio, with an optional HTTP mode.

> **Mixed backend.** Reads come from the local Signal Desktop database. Sends need `signal-cli` installed and linked separately; without it, read and search still work.

## Setup

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Signal Desktop with local history, and (for sends) `signal-cli`.

```bash
git clone https://github.com/Sealjay/mcp-signal.git
cd mcp-signal
uv sync
brew install signal-cli   # optional, sends only
```

Tested with `signal-cli` 0.14.8; 0.14.9 changes nothing this server uses.

### Configure sends

Put machine-local config in `.env.local` at the repo root (gitignored):

```bash
echo 'SIGNAL_ACCOUNT="+441234567890"' > .env.local
```

| Variable | Purpose |
|----------|---------|
| `SIGNAL_ACCOUNT` | Linked `signal-cli` account used for sends |
| `SIGNAL_CLI_PATH` | Override the `signal-cli` binary path |
| `SIGNAL_DATA_DIR` | Override the Signal Desktop data directory |
| `SIGNAL_DB_PASSWORD` / `SIGNAL_DB_KEY` | Password or raw key for an encrypted desktop DB |
| `SIGNAL_JSONRPC_TIMEOUT_SECONDS` | `signal-cli` JSON-RPC timeout. Default 30, max 300 |
| `MCP_AUTH_TOKEN` | Bearer token for HTTP mode (all routes except `/health`). Unset means no auth |
| `MCP_LISTEN_ADDR` | `host:port` for HTTP mode; setting it enables HTTP mode. Default `0.0.0.0:8765` |

Shell variables override `.env.local`. `.env.local` only loads `SIGNAL_*` keys, so set `MCP_*` in the shell.

### Link `signal-cli` (first run)

```bash
signal-cli link -n "signal-mcp"   # scan the QR: Signal app > Settings > Linked Devices
signal-cli listAccounts           # should match SIGNAL_ACCOUNT
uv run signal-mcp smoke
```

`signal-cli` keeps its linked-device state in its own data directory (usually `~/.local/share/signal-cli/data`), outside this repo.

### HTTP mode (optional)

```bash
uv run signal-mcp serve --http --listen-addr 0.0.0.0:8765
```

Streamable HTTP at `/mcp`. It is stateless (no `Mcp-Session-Id`, and `GET /mcp` returns 405 because there is no standalone SSE stream) and serves MCP 2026-07-28 as well as older revisions.

## MCP client configuration

Every client launches the server over stdio with the same block. Use an absolute repo path.

```json
{
  "mcpServers": {
    "signal": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp-signal", "signal-mcp", "serve"]
    }
  }
}
```

| Client | Where |
|--------|-------|
| Claude Code | `claude mcp add --transport stdio signal --scope user -- uv run --directory /absolute/path/to/mcp-signal signal-mcp serve`, or the block above in `.mcp.json` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json` |

Restart the client afterwards. If a GUI app reports `spawn uv ENOENT`, set `command` to the absolute path from `which uv` (Homebrew: `/opt/homebrew/bin/uv`).

## Tools

| Tool | Purpose |
|------|---------|
| `list_chats` | List direct and group chats from Signal Desktop |
| `read_messages` | Read messages from a specific chat |
| `search_messages` | Search messages within one chat or across all chats |
| `list_groups` | List groups from `signal-cli`, including group IDs |
| `chat_activity` | Rank chats by recent activity, with last-message/last-reply dates and unanswered-inbound counts |
| `decrypt_attachment` | Decrypt a locally stored attachment and return the decrypted file's path |
| `send_message` | Send text to a phone number, group ID or exact chat name. `chat_name` resolves to the contact's service ID when their number is hidden |
| `get_status` | Show desktop DB / `signal-cli` / account readiness |
| `pairing_status` | Report `signal-cli` link state and surface the live link QR |

Prompts: `summarise_chat` and `discover_topics`.

## Architecture

| Component | Description |
|-----------|-------------|
| MCP server | Python/FastMCP 4, stdio or stateless streamable HTTP |
| Read path | `signal-export` against the local Signal Desktop database |
| Send path | `signal-cli -a ACCOUNT jsonRpc`, launched on demand |
| State | No cache; reads Signal Desktop data directly |

## Privacy and limitations

- No cloud relay; data stays on your machine. HTTP mode is opt-in, and bearer auth applies only when `MCP_AUTH_TOKEN` is set (the default bind is `0.0.0.0`).
- **Prompt injection:** this server has [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/). A malicious incoming message could try to make an agent exfiltrate others, so review outbound actions before approving them.
- Text-only sends; no real-time notifications; one account per instance.
- Group sends need `signal-cli`; the desktop DB alone cannot address groups safely.
- Read metadata comes from Signal Desktop, not `signal-cli`. Voice notes are flagged `is_voice_note` from Desktop's attachment flag.

Report vulnerabilities via [`SECURITY.md`](SECURITY.md).

## Troubleshooting

- **`signal-cli` not found:** put it on `PATH` or set `SIGNAL_CLI_PATH`.
- **Reads work, sends fail:** `signal-cli` is not linked or `SIGNAL_ACCOUNT` is unset. Check `signal-cli listAccounts`.
- **`[403] Authorization failed`:** the linked device was removed or expired. Re-link with `signal-cli link -n "signal-mcp"`.
- **`signal-cli link` hangs:** don't pass `-a`/`--account` to `link`.
- **No messages returned:** confirm Signal Desktop is installed and has history.

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
uv run signal-mcp smoke
```

CI runs the same on every pull request. See [`CLAUDE.md`](CLAUDE.md) for structure and constraints.

## Licence

MIT. See [LICENSE](LICENSE).
