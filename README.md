# mcp-signal

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=ffffff)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-package%20manager-4B5563)](https://docs.astral.sh/uv/)
[![MCP](https://img.shields.io/badge/MCP-Model_Context_Protocol-6E44FF)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/github/license/Sealjay/mcp-signal)](LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/Sealjay/mcp-signal)](https://github.com/Sealjay/mcp-signal/issues)
[![GitHub stars](https://img.shields.io/github/stars/Sealjay/mcp-signal?style=social)](https://github.com/Sealjay/mcp-signal)
[![Sealjay/mcp-signal MCP server](https://glama.ai/mcp/servers/Sealjay/mcp-signal/badges/score.svg)](https://glama.ai/mcp/servers/Sealjay/mcp-signal)

> A local Model Context Protocol (MCP) server that reads Signal Desktop history from the local encrypted database via [`signal-export`](https://github.com/carderne/signal-export) and sends outbound messages via [`signal-cli`](https://github.com/AsamK/signal-cli).

mcp-signal focuses on the core workflow for personal Signal automation — list chats, read messages, search messages, inspect groups, and send messages to direct or group chats. Everything runs locally; stdio transport with no network listener.

> **Heads up — mixed backend.** Read/search comes from the local Signal Desktop database. Sending uses `signal-cli`, which must be installed and linked to a Signal account separately. If `signal-cli` is unavailable, read/search still works but send tools do not.

## Features

- List direct and group chats from Signal Desktop
- Read recent messages from a chat
- Search messages within one chat or across all chats
- List group chats with `signal-cli` group IDs for outbound use
- Send a message to:
  - a direct recipient by phone number
  - a group by group ID
  - a chat by exact chat name (with ambiguity checks)
- Runs entirely on your machine; stdio transport with no network listener

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Signal Desktop with an existing local message database
- [`signal-cli`](https://github.com/AsamK/signal-cli) installed and linked if you want outbound sends

### Installation

1. **Clone this repository**

   ```bash
   git clone https://github.com/Sealjay/mcp-signal.git
   cd mcp-signal
   ```

2. **Install dependencies**

   ```bash
   uv sync
   ```

3. **Install `signal-cli`** (optional — only needed for outbound sends)

   On macOS, the simplest route is Homebrew:

   ```bash
   brew install signal-cli
   ```

### Configure outbound sends

The server auto-loads a local `.env.local` file from the repo root if present. This file is gitignored and is the recommended place for machine-local config.

```bash
cat > .env.local <<'EOF'
SIGNAL_ACCOUNT="+441234567890"
EOF
```

Optional environment variables:

| Variable | Purpose |
|----------|---------|
| `SIGNAL_CLI_PATH` | Override the `signal-cli` binary path |
| `SIGNAL_DATA_DIR` | Override the Signal Desktop data directory |
| `SIGNAL_DB_PASSWORD` | Password for encrypted desktop DBs if needed |
| `SIGNAL_DB_KEY` | Raw key for encrypted desktop DBs if needed |

Environment variables set in the shell take precedence over `.env.local`.

### Link `signal-cli` (first run only)

`mcp-signal` does not manage linking itself. Link the local `signal-cli` device first:

```bash
signal-cli link -n "signal-mcp"
```

Scan the QR code in the Signal mobile app (*Settings → Linked Devices → Link New Device*).

Do **not** pass `-a` / `--account` to `link` on current `signal-cli` versions — linking a new secondary device does not take a phone number there.

After the QR is accepted, confirm the linked account is visible:

```bash
signal-cli listAccounts
```

That account should match the `SIGNAL_ACCOUNT` value in `.env.local`.

`signal-cli` stores its linked-account state under its own local data directory (typically `~/.local/share/signal-cli/data` on macOS/Linux). That state lives **outside this repository** and is **not committed** by `mcp-signal`.

Verify everything is connected:

```bash
uv run signal-mcp smoke
```

## MCP client configuration

All clients launch the server the same way over stdio. On macOS, you may need the absolute path to `uv` — see [macOS: `uv` PATH](#macos-uv-path) below.

### Claude Code

The quickest route is the CLI:

```bash
claude mcp add --transport stdio signal --scope user -- uv run --directory /absolute/path/to/mcp-signal signal-mcp serve
```

Alternatively, add to `.mcp.json` at your project root (or `~/.claude.json` for a user-scoped server):

```json
{
  "mcpServers": {
    "signal": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp-signal", "signal-mcp", "serve"]
    }
  }
}
```

If you edit the file directly, restart the Claude Code session to pick it up.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

Restart Claude Desktop. You should see `signal` listed as an available integration.

### Cursor

Add to `~/.cursor/mcp.json`:

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

Restart Cursor.

### macOS: `uv` PATH

GUI apps (Claude Desktop, Cursor) don't always inherit the PATH from your interactive terminal, so `uv` may fail with `spawn uv ENOENT`. Fix by using the absolute path to `uv` in `command`:

- **Homebrew** — `/opt/homebrew/bin/uv` (Apple Silicon) or `/usr/local/bin/uv` (Intel)
- **Manual install** — run `which uv` in your terminal to find it

Example:

```json
{
  "mcpServers": {
    "signal": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp-signal", "signal-mcp", "serve"]
    }
  }
}
```

## Architecture

| Component | Description |
|-----------|-------------|
| MCP server | Python/FastMCP, stdio transport |
| Read path | `signal-export` reading the local Signal Desktop database |
| Send path | `signal-cli` JSON-RPC launched on demand |
| State | No separate cache; reads directly from Signal Desktop data |

### Data flow

1. The MCP client launches `signal-mcp serve` over stdio.
2. Read/search tools call `signal-export` against the local Signal Desktop database.
3. Group listing and outbound sends call `signal-cli -a ACCOUNT jsonRpc`.
4. Results are returned as structured JSON.

### Project structure

```text
mcp-signal/
  src/mcp_signal/
    config.py
    main.py
    reader.py
    server.py
    signal_cli.py
  tests/
  CLAUDE.md
  LICENSE
  README.md
  SECURITY.md
```

## Tools

| Tool | Purpose |
|------|---------|
| `list_chats` | List direct and group chats from Signal Desktop |
| `read_messages` | Read messages from a specific chat |
| `search_messages` | Search messages within one chat or across all chats |
| `list_groups` | List groups from `signal-cli`, including group IDs |
| `send_message` | Send a text message to a direct recipient or group |
| `get_status` | Show desktop DB / `signal-cli` / account readiness |

## Privacy and security

- No cloud relay. No network listener. All data stays on your machine.
- Read/search uses your local Signal Desktop data only.
- Send operations require a locally configured `signal-cli` account.
- `.env.local` is intended for local secrets such as `SIGNAL_ACCOUNT` and is not committed.
- `signal-cli` linked-device state is stored in its own local app data directory, outside this repo, and is not committed.

See [`SECURITY.md`](SECURITY.md) for how to report vulnerabilities.

## Limitations

- **Prompt-injection risk:** as with many MCP servers, this one is subject to [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/). Malicious incoming messages could attempt to instruct an agent to exfiltrate other messages. Treat the tool surface accordingly and review outbound actions before approving them.
- **Mixed backend:** chat history comes from Signal Desktop, while outbound sends come from `signal-cli`.
- **No attachments:** text-only send.
- **No real-time notifications:** polling/read only.
- **Single account** per MCP instance.
- **Group sends need `signal-cli`:** local DB reads alone do not provide enough information to send to groups safely.

## Development

```bash
uv sync
uv run signal-mcp smoke
uv run pytest
uv run ruff check .
```

## Troubleshooting

- **`signal-cli` not found** — confirm `signal-cli` is on `PATH` or set `SIGNAL_CLI_PATH` in `.env.local`. On macOS, `brew install signal-cli` is the simplest route.
- **Read/search works but sends fail** — `signal-cli` is not linked or `SIGNAL_ACCOUNT` is not set. Run `signal-cli listAccounts` to verify, then check `.env.local`.
- **`signal-cli link` hangs or fails** — do not pass `-a` / `--account` to `link` on current versions. Run `signal-cli link -n "signal-mcp"` and scan the QR from your phone.
- **MCP client can't launch the server** — `args` must contain an absolute path to the repo, not relative. If `uv` itself fails with `spawn uv ENOENT`, see [macOS: `uv` PATH](#macos-uv-path).
- **No messages returned** — confirm Signal Desktop is installed and has message history. The read path queries the local Signal Desktop database directly.

## Contributing

Contributions welcome via pull request. Please:

- Run `uv run ruff check .` before pushing.
- Ensure `uv run pytest` passes.

See [`CLAUDE.md`](CLAUDE.md) for the full development workflow.

## Licence

MIT Licence — see [LICENSE](LICENSE).
