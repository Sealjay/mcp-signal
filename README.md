# mcp-signal

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=ffffff)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-package%20manager-4B5563)](https://docs.astral.sh/uv/)
[![MCP](https://img.shields.io/badge/MCP-Model_Context_Protocol-6E44FF)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/github/license/Sealjay/mcp-signal)](LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/Sealjay/mcp-signal)](https://github.com/Sealjay/mcp-signal/issues)

> A local Model Context Protocol (MCP) server that reads Signal Desktop history from the local encrypted database via [`signal-export`](https://github.com/carderne/signal-export) and sends outbound messages via [`signal-cli`](https://github.com/AsamK/signal-cli).

`mcp-signal` is deliberately smaller than `mcp-whatsapp`: it focuses on the core workflow needed for personal automation right now — list chats, read messages, search messages, inspect groups, and send messages to direct or group chats. Everything runs locally.

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

```bash
git clone https://github.com/Sealjay/mcp-signal.git
cd mcp-signal
uv sync
```

Install `signal-cli` if you want outbound sends. On macOS, the simplest route is Homebrew:

```bash
brew install signal-cli
```

### Configure outbound sends

The server auto-loads a local `.env.local` file from the repo root if present. This file is gitignored and is the recommended place for machine-local config.

Example:

```bash
cat > .env.local <<'EOF'
SIGNAL_ACCOUNT="+441234567890"
EOF
```

Optional:

- `SIGNAL_CLI_PATH` — override the `signal-cli` binary path
- `SIGNAL_DATA_DIR` — override the Signal Desktop data directory
- `SIGNAL_DB_PASSWORD` — password for encrypted desktop DBs if needed
- `SIGNAL_DB_KEY` — raw key for encrypted desktop DBs if needed

Environment variables set in the shell still take precedence over `.env.local`.

### Link `signal-cli` (first run only)

`mcp-signal` does not manage linking itself. Link the local `signal-cli` device first:

```bash
signal-cli link -n "signal-mcp"
```

Then scan the QR code in the Signal mobile app.

Do **not** pass `-a` / `--account` to `link` on current `signal-cli` versions — linking a new secondary device does not take a phone number there.

After the QR is accepted, confirm the linked account is visible:

```bash
signal-cli listAccounts
```

That account should match the `SIGNAL_ACCOUNT` value in your local `.env.local`.

After linking, a quick local readiness check is:

```bash
uv run signal-mcp smoke
```

and then:

```bash
uv run python - <<'PY'
from mcp_signal.config import load_config
print(load_config())
PY
```

## MCP client configuration

All clients launch the server the same way over stdio:

### Claude Code

```bash
claude mcp add --transport stdio signal --scope user -- uv run --directory /absolute/path/to/mcp-signal signal-mcp serve
```

Or in `.mcp.json`:

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

### Claude Desktop

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

### Cursor

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

## Available tools

Six tools in the first release.

| Tool | Purpose |
|------|---------|
| `list_chats` | List direct and group chats from Signal Desktop |
| `read_messages` | Read messages from a specific chat |
| `search_messages` | Search messages within one chat or across all chats |
| `list_groups` | List groups from `signal-cli`, including group IDs |
| `send_message` | Send a text message to a direct recipient or group |
| `get_status` | Show desktop DB / `signal-cli` / account readiness |

## Privacy and security

- No cloud relay.
- No network listener.
- Read/search uses your local Signal Desktop data only.
- Send operations require a locally configured `signal-cli` account.
- `.env.local` is intended for local secrets such as `SIGNAL_ACCOUNT` and is not committed.
- This tool surface is subject to prompt-injection risks from untrusted message content. Review outbound actions carefully.

## Limitations

- **Mixed backend:** chat history comes from Signal Desktop, while outbound sends come from `signal-cli`.
- **No attachments:** first release is text-only send.
- **No real-time notifications:** polling/read only.
- **Single account** per MCP instance.
- **Prompt-injection risk:** as with many MCP servers, malicious incoming content could try to influence an agent using the tools.
- **Group sends need `signal-cli`:** local DB reads alone do not provide enough information to send to groups safely.

## Development

```bash
uv sync
uv run signal-mcp smoke
uv run pytest
uv run ruff check .
```
