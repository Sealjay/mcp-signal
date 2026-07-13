---
paths:
  - "src/mcp_signal/server.py"
  - "src/mcp_signal/signal_cli.py"
---

# MCP Tool Description Quality (Glama.ai)

When writing or updating MCP tool descriptions in `src/mcp_signal/server.py` (the `@mcp.tool()`-decorated functions and their `Annotated[..., Field(description=...)]` parameters), follow these guidelines to score well on Glama.ai's quality dimensions. This repo publishes a `glama.json`, so these descriptions are scored.

## Required in every description

1. **Purpose with specific verb and resource** — "Send a text message via Signal to a direct recipient or group" not "Send a message"
2. **Side effects** — state what changes: "Delivers a real message through signal-cli" or "Read-only with no side effects" or "Writes a decrypted copy to a temporary directory"
3. **Reversibility** — for write operations, state that they are not reversible: "Sends are not reversible from this server (Signal supports user-initiated message deletion only via the official clients)". Read-only tools should say so explicitly.
4. **Return shape** — "Returns target_type, target identifier, and timestamp on success" or "Each result includes name, phone number, message count, and a preview of the last message"
5. **When to use vs alternatives** — "Use this to obtain group_id values needed by send_message. Use list_chats instead for a combined view of both direct and group chats"

## Required in parameter descriptions

1. **Which identifier and where it comes from** — Signal has three distinct addressing modes for `send_message`:
   - `phone_number`: E.164 format with leading `+` (e.g. `+441234567890`)
   - `group_id`: opaque group identifier as returned by `list_groups`
   - `chat_name`: exact case-sensitive name as returned by `list_chats`
   Always tell the agent which `list_*` tool produced the ID it should pass.
2. **Constraints** — call out valid ranges, formats, and mutual exclusivity. Numeric limits in this codebase: `limit` is clamped to 1-200 (`_MAX_LIMIT`), `offset` to 0-10000 (`_MAX_OFFSET`). The three recipient fields on `send_message` are mutually exclusive.
3. **Defaults** — state default values for optional params (e.g. `limit=50`, `limit=20`, `offset=0`, empty-string `query` returns all results).
4. **Datetime formats** — `after` / `before` on `read_messages` are ISO 8601 strings; include an example like `'2025-01-15T00:00:00'`.
5. **Rate limits** — `send_message` is gated by a 1s per-recipient cooldown and a 10-messages-per-60s global burst limit. Disclose this so agents know to expect throttling errors.
6. **Prerequisites** — `send_message` requires `signal-cli` to be installed and `SIGNAL_ACCOUNT` configured; tell agents to call `get_status` first to verify `send_available` is true.

## Style

- Front-load the purpose (first sentence = what it does).
- Keep total description under 3 sentences when possible; the existing tools follow a "purpose sentence — return shape / side effects — when-to-use" three-beat pattern. Mirror it.
- Don't repeat what the schema already says (parameter names, types).
- Use consistent terminology: "Signal message", "chat", "direct recipient", "group", "group_id", "phone number". Don't mix "conversation" / "thread" / "channel".
- British English for prose, American English in code identifiers.

## Avoid

- Descriptions that only restate the function name (e.g. "Lists groups" for `list_groups`).
- Missing side-effect disclosure on write operations (`send_message`, `decrypt_attachment`).
- Missing ID-source guidance — agents need to know whether to call `list_chats` or `list_groups` to get the right field.
- Missing rate-limit disclosure on `send_message`.
- Missing prerequisite disclosure (signal-cli availability, SIGNAL_ACCOUNT) on tools that need them.
- Emoji in descriptions.
