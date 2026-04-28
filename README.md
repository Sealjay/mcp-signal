# mcp-signal

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=ffffff)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.x-6E44FF)](https://gofastmcp.com/)
[![MCP](https://img.shields.io/badge/MCP-Model_Context_Protocol-6E44FF)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENCE)

> A local MCP server that gives Claude read-only access to your [Signal Desktop](https://signal.org/download/) message history via the local encrypted database.

Fork of [stefanstranger/signal-mcp-server](https://github.com/stefanstranger/signal-mcp-server) with added activity tracking, date filtering, group chat sender resolution, and FastMCP 3.x.

## Features

- List all Signal chats sorted by most recent message
- Retrieve messages from any chat with pagination and date range filtering
- Full-text search within a specific chat
- Per-chat activity dashboard: last message, last reply, unread count
- Correct sender attribution in group chats
- Runs entirely on your machine; stdio transport with no network exposure

## Setup

### Prerequisites

- [Python 3.13+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/) package manager
- Signal Desktop installed with an existing message database

### Installation

```bash
git clone https://github.com/Sealjay/mcp-signal.git
cd mcp-signal
uv sync
```

### Signal data directory

The server automatically detects your Signal data directory:

- **macOS**: `~/Library/Application Support/Signal`
- **Windows**: `%APPDATA%\Signal`
- **Linux**: `~/.config/Signal` (or Flatpak: `~/.var/app/org.signal.Signal/config/Signal`)

## MCP client configuration

### Claude Code

Add to `.mcp.json` at your project root:

```json
{
  "mcpServers": {
    "signal": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp-signal", "fastmcp", "run", "server.py"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "signal": {
      "command": "/path/to/uv",
      "args": ["run", "--directory", "/absolute/path/to/mcp-signal", "fastmcp", "run", "server.py"]
    }
  }
}
```

### macOS: `uv` PATH

GUI apps don't always inherit your shell PATH. Use the absolute path to `uv`:

- **Default install**: `~/.local/bin/uv`
- **Homebrew**: `/opt/homebrew/bin/uv`

## Tools

5 tools, all read-only.

| Tool | Purpose |
|------|---------|
| `signal_list_chats` | List all chats with contact details, message count, and last message date. Sorted by most recent. |
| `signal_get_chat_messages` | Retrieve messages from a specific chat with pagination (`limit`, `offset`) and date range filtering (`after`, `before` as ISO datetime). |
| `signal_search_chat` | Full-text search within a specific chat's messages. |
| `signal_chat_activity` | Per-chat activity summary: last message date/sender, last reply date, unread count. Sorted by most recent. |

### Encryption

If your Signal database is encrypted, pass `password` or `key` parameters to any tool.

## Architecture

| Component | Description |
|-----------|-------------|
| MCP server | Python/FastMCP 3.x, stdio transport |
| Data access | [signal-export](https://github.com/carderne/signal-export) library reads the Signal Desktop SQLite database |
| Transport | stdio only - no network listener |

### Data flow

1. MCP client launches `fastmcp run server.py` over stdio.
2. Tool calls read directly from Signal Desktop's local encrypted SQLite database.
3. Messages are decrypted in-process using the key from Signal's config.
4. Results are returned as structured JSON.

No data leaves your machine. The server is entirely read-only - it cannot send messages or modify your Signal database.

## Privacy and security

- **Read-only**: the server cannot send messages, modify contacts, or alter your Signal database in any way.
- **Local only**: stdio transport, no network listener, no telemetry.
- **No credentials stored**: the Signal Desktop database key is read from Signal's own config directory at runtime.
- **Prompt-injection risk**: as with many MCP servers, this one is subject to [the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/). A malicious message could attempt to instruct Claude to exfiltrate other messages. Treat the tool surface accordingly.

## Limitations

- **Read-only**: no sending capability. Use Signal Desktop or another client to send messages.
- **Signal Desktop required**: the server reads from Signal Desktop's local database. Signal mobile-only users cannot use this.
- **No real-time notifications**: polling only.
- **Single account** per Signal Desktop installation.

## Troubleshooting

- **"Signal database not found"** - ensure Signal Desktop is installed and has been opened at least once. Check that the data directory path is correct.
- **"Database is encrypted"** - you may need to provide `password` or `key` parameters. Signal databases are encrypted by default on most platforms.
- **"No messages found"** - verify the chat name is spelled correctly. Try `signal_list_chats` first to see available chat names.
- **Server won't start** - ensure Python 3.13+ is installed and `uv sync` completed successfully.

## Credits

This project builds upon [signal-export](https://github.com/carderne/signal-export) by [Chris Arderne](https://github.com/carderne) for Signal Desktop database access, and was originally forked from [stefanstranger/signal-mcp-server](https://github.com/stefanstranger/signal-mcp-server).

## Licence

MIT Licence
