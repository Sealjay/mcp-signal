from __future__ import annotations

import time
from collections import deque
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from .config import SignalConfig, load_config
from .link_manager import LinkManager
from .reader import DesktopReader
from .signal_cli import SignalCLIClient, SignalCLIError

_MAX_LIMIT = 200
_MAX_OFFSET = 10_000


def build_server(config: SignalConfig | None = None) -> FastMCP:
    cfg = config or load_config()
    reader = DesktopReader(cfg)
    signal_cli = SignalCLIClient(cfg)
    link_manager = LinkManager(cfg)

    _last_send_times: dict[str, float] = {}
    _SEND_COOLDOWN_SECONDS = 1.0

    # Global rate limit: at most _GLOBAL_SEND_BURST sends in _GLOBAL_SEND_WINDOW seconds.
    _global_send_window: deque[float] = deque()
    _GLOBAL_SEND_WINDOW = 60.0
    _GLOBAL_SEND_BURST = 10

    def _record_send(key: str) -> None:
        now = time.monotonic()
        _last_send_times[key] = now
        _global_send_window.append(now)

    mcp = FastMCP(
        "Signal MCP Server",
        version="0.2.0",
        strict_input_validation=True,
        mask_error_details=True,
    )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def get_status() -> dict[str, Any]:
        """Check whether the Signal MCP server can read local messages
        and send outbound messages.

        Returns boolean fields: source_dir_exists,
        signal_cli_available, signal_account_configured,
        read_available, send_available. Read-only with no side
        effects. Call this before read or send operations to verify
        configuration; call pairing_status instead to check first-run
        device-linking state.
        """
        source_dir_exists = cfg.source_dir.exists()
        return {
            "source_dir_exists": source_dir_exists,
            "signal_cli_available": cfg.signal_cli_available,
            "signal_account_configured": bool(cfg.signal_account),
            "read_available": source_dir_exists,
            "send_available": (
                cfg.signal_cli_available and bool(cfg.signal_account)
            ),
        }

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    def pairing_status() -> dict[str, Any]:
        """Report the Signal device-linking setup state for first-run
        pairing, so a client can surface the live link QR.

        Returns a setup_state envelope: state 'ready' with the linked
        account once signal-cli is linked; 'awaiting_qr' with a
        'qr_payload' sgnl://linkdevice URI to scan in Signal (Settings →
        Linked devices → Link new device) while a link is in progress
        (no payload yet on the first call, until the URI is captured); or
        'error' when signal-cli is unavailable. Read-only from the
        caller's view, but the first call on an unlinked device starts a
        background signal-cli link process as a side effect. Poll this to
        drive a pairing UI; call get_status instead to check read/send
        availability once linked.
        """
        return link_manager.pairing_status()

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def list_chats(
        query: Annotated[
            str,
            Field(
                description=(
                    "Case-insensitive substring to filter by chat"
                    " name or phone number. Empty string returns"
                    " all chats."
                ),
            ),
        ] = "",
        limit: Annotated[
            int,
            Field(
                description=(
                    "Maximum number of chats to return,"
                    " between 1 and 200. Defaults to 50."
                ),
            ),
        ] = 50,
    ) -> list[dict[str, Any]]:
        """List direct and group Signal chats from the local desktop
        database, sorted by most recent message.

        Each result includes name, phone number, message count, and a
        preview of the last message. Read-only with no side effects.
        Use this to discover exact chat names before calling
        read_messages or search_messages. Use list_groups instead when
        you need group_id values for send_message.
        """
        limit = min(max(limit, 1), _MAX_LIMIT)
        return reader.list_chats(query=query, limit=limit)

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def read_messages(
        chat_name: Annotated[
            str,
            Field(
                description=(
                    "Exact chat name as returned by list_chats"
                    " (case-sensitive)."
                ),
            ),
        ],
        limit: Annotated[
            int,
            Field(
                description=(
                    "Maximum number of messages to return,"
                    " between 1 and 200. Defaults to 20."
                ),
            ),
        ] = 20,
        offset: Annotated[
            int,
            Field(
                description=(
                    "Number of messages to skip from the most"
                    " recent, for pagination (0-10000)."
                    " Defaults to 0."
                ),
            ),
        ] = 0,
        after: Annotated[
            str | None,
            Field(
                description=(
                    "ISO 8601 datetime; only return messages sent"
                    " after this time, e.g."
                    " '2025-01-15T00:00:00'."
                ),
            ),
        ] = None,
        before: Annotated[
            str | None,
            Field(
                description=(
                    "ISO 8601 datetime; only return messages sent"
                    " before this time, e.g."
                    " '2025-02-01T00:00:00'."
                ),
            ),
        ] = None,
    ) -> list[dict[str, Any]]:
        """Read messages from a single Signal chat, returned
        newest-first.

        Each message includes sender, date, body text, reactions, and
        attachment metadata. Read-only with no side effects. Requires
        an exact chat name from list_chats. Use search_messages
        instead to find messages by keyword across chats.
        """
        limit = min(max(limit, 1), _MAX_LIMIT)
        offset = min(max(offset, 0), _MAX_OFFSET)
        return reader.read_messages(
            chat_name,
            limit=limit,
            offset=offset,
            after=after,
            before=before,
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def search_messages(
        query: Annotated[
            str,
            Field(
                description=(
                    "Case-insensitive substring to search for"
                    " within message bodies."
                ),
            ),
        ],
        chat_name: Annotated[
            str | None,
            Field(
                description=(
                    "Exact chat name to restrict the search to a"
                    " single chat. Omit to search across all"
                    " chats."
                ),
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                description=(
                    "Maximum number of matching messages to"
                    " return, between 1 and 200. Defaults to 20."
                ),
            ),
        ] = 20,
    ) -> list[dict[str, Any]]:
        """Search Signal message bodies for a keyword, within one
        chat or across all chats, returned newest-first.

        Each result includes sender, date, chat name, body text,
        reactions, and attachment metadata. Read-only with no side
        effects. Use this to find messages by content. Use
        read_messages instead to browse a specific chat
        chronologically.
        """
        limit = min(max(limit, 1), _MAX_LIMIT)
        return reader.search_messages(
            query=query, chat_name=chat_name, limit=limit
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def list_groups(
        query: Annotated[
            str,
            Field(
                description=(
                    "Case-insensitive substring to filter group"
                    " names. Empty string returns all groups."
                ),
            ),
        ] = "",
        limit: Annotated[
            int,
            Field(
                description=(
                    "Maximum number of groups to return,"
                    " between 1 and 200. Defaults to 50."
                ),
            ),
        ] = 50,
    ) -> list[dict[str, Any]]:
        """List Signal groups with group_id, name, description,
        members, and admin lists, sorted alphabetically.

        Read-only with no side effects. Queries signal-cli when
        available; falls back to the local desktop database (without
        group_id). Use this to obtain group_id values needed by
        send_message. Use list_chats instead for a combined view of
        both direct and group chats.
        """
        limit = min(max(limit, 1), _MAX_LIMIT)
        try:
            return signal_cli.list_groups(query=query, limit=limit)
        except SignalCLIError:
            return reader.list_local_groups(query=query, limit=limit)

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def chat_activity(
        limit: Annotated[
            int,
            Field(
                description=(
                    "Maximum number of chats to return,"
                    " between 1 and 200. Defaults to 50."
                ),
            ),
        ] = 50,
    ) -> list[dict[str, Any]]:
        """List Signal chats ranked by recent activity, showing last
        message date, last reply date, and count of unanswered
        inbound messages.

        Read-only with no side effects. Use this to identify chats
        that need a response. Use list_chats instead for a general
        chat directory with message previews.
        """
        limit = min(max(limit, 1), _MAX_LIMIT)
        return reader.chat_activity(limit=limit)

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def decrypt_attachment(
        encrypted_path: Annotated[
            str,
            Field(
                description=(
                    "Absolute filesystem path to the encrypted"
                    " attachment file, as returned in the"
                    " 'encrypted_path' field of message"
                    " attachment metadata."
                ),
            ),
        ],
        local_key: Annotated[
            str,
            Field(
                description=(
                    "Base64-encoded 64-byte key (32-byte AES-CBC"
                    " + 32-byte HMAC-SHA256), from the"
                    " 'local_key' field of attachment metadata."
                ),
            ),
        ],
    ) -> str:
        """Decrypt a locally stored Signal attachment and return the
        path to the decrypted file.

        The encrypted_path and local_key values come from attachment
        metadata in read_messages or search_messages results.
        Read-only on Signal data; writes a decrypted copy to a
        temporary directory (the temp file is not auto-cleaned).
        Returns the absolute path to the decrypted file as a string
        on success, or a string starting with 'Error:' on failure
        (missing file, wrong key length, or HMAC mismatch). Use this
        after reading messages that contain attachments.
        """
        import base64
        import hashlib
        import hmac as hmac_mod
        import tempfile
        from pathlib import Path

        src_path = Path(encrypted_path)
        if not src_path.exists():
            return f"Error: attachment not found at {encrypted_path}"

        key_bytes = base64.b64decode(local_key)
        if len(key_bytes) != 64:
            return (
                f"Error: expected 64-byte key, got {len(key_bytes)}"
            )

        cipher_key = key_bytes[:32]
        mac_key = key_bytes[32:]

        data = src_path.read_bytes()
        iv = data[:16]
        their_mac = data[-32:]
        ciphertext = data[16:-32]

        our_mac = hmac_mod.new(
            mac_key, iv + ciphertext, hashlib.sha256
        ).digest()
        if not hmac_mod.compare_digest(our_mac, their_mac):
            return "Error: HMAC verification failed"

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers import (
            Cipher,
            algorithms,
            modes,
        )

        cipher = Cipher(
            algorithms.AES(cipher_key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        pad_len = plaintext[-1]
        if 1 <= pad_len <= 16:
            plaintext = plaintext[:-pad_len]

        ext = ".bin"
        if plaintext[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif plaintext[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif plaintext[:4] == b"GIF8":
            ext = ".gif"
        elif plaintext[:4] == b"RIFF":
            ext = ".webp"

        tmp_dir = tempfile.mkdtemp(prefix="signal-att-")
        out_path = Path(tmp_dir) / f"attachment{ext}"
        out_path.write_bytes(plaintext)

        return str(out_path)

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    def send_message(
        message: Annotated[
            str,
            Field(description="The text message content to send."),
        ],
        phone_number: Annotated[
            str | None,
            Field(
                description=(
                    "Recipient phone number in E.164 format"
                    " (e.g. '+441234567890'). Mutually exclusive"
                    " with group_id and chat_name."
                ),
            ),
        ] = None,
        group_id: Annotated[
            str | None,
            Field(
                description=(
                    "Target group ID as returned by list_groups."
                    " Mutually exclusive with phone_number and"
                    " chat_name."
                ),
            ),
        ] = None,
        chat_name: Annotated[
            str | None,
            Field(
                description=(
                    "Exact chat name from list_chats;"
                    " auto-resolves to the matching phone_number"
                    " or group_id. Mutually exclusive with the"
                    " other two recipient fields."
                ),
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Send a text message via Signal to a direct recipient or
        group.

        This is a write operation that delivers a real message through
        signal-cli. Sends are not reversible from this server — Signal
        supports user-initiated message deletion only via the official
        clients. Exactly one of phone_number, group_id, or chat_name
        must be supplied; providing zero or more than one raises an
        error. Rate-limited to 1 message per recipient per second and
        10 messages per 60-second window globally. Requires signal-cli
        and SIGNAL_ACCOUNT to be configured — call get_status first to
        verify send_available is true. Returns target_type, target
        identifier, and timestamp on success.
        """
        provided = [
            value is not None and value != ""
            for value in (phone_number, group_id, chat_name)
        ]
        if sum(provided) != 1:
            raise ValueError(
                "Provide exactly one of phone_number,"
                " group_id, or chat_name"
            )

        target_key = phone_number or group_id or chat_name or ""
        now = time.monotonic()

        # Per-recipient cooldown
        last = _last_send_times.get(target_key, 0.0)
        if now - last < _SEND_COOLDOWN_SECONDS:
            raise ValueError(
                "Rate limit: please wait before sending another"
                " message to the same recipient"
            )

        # Global burst limit
        while (
            _global_send_window
            and _global_send_window[0] < now - _GLOBAL_SEND_WINDOW
        ):
            _global_send_window.popleft()
        if len(_global_send_window) >= _GLOBAL_SEND_BURST:
            raise ValueError(
                f"Global rate limit reached: at most"
                f" {_GLOBAL_SEND_BURST} messages"
                f" per {int(_GLOBAL_SEND_WINDOW)}s window"
            )

        if phone_number:
            result = signal_cli.send_direct_message(
                phone_number, message
            )
            _record_send(target_key)
            return result
        if group_id:
            result = signal_cli.send_group_message(
                group_id, message
            )
            _record_send(target_key)
            return result
        assert chat_name is not None

        direct_matches = reader.find_direct_chat_matches(chat_name)
        group_matches = signal_cli.find_group_matches(chat_name)

        if direct_matches and group_matches:
            raise ValueError(
                "Ambiguous chat name; specify phone_number"
                " or group_id explicitly"
            )
        if len(direct_matches) > 1:
            raise ValueError(
                "Multiple direct chats matched;"
                " specify phone_number explicitly"
            )
        if len(group_matches) > 1:
            raise ValueError(
                "Multiple groups matched;"
                " specify group_id explicitly"
            )
        if len(direct_matches) == 1:
            number = direct_matches[0].get("number")
            if not number:
                raise ValueError(
                    "Matched chat has no phone number"
                    " available for sending"
                )
            result = signal_cli.send_direct_message(number, message)
            result["resolved_name"] = chat_name
            _record_send(target_key)
            return result
        if len(group_matches) == 1:
            resolved_group_id = group_matches[0].get("group_id")
            if not resolved_group_id:
                raise ValueError(
                    "Matched group has no group_id"
                    " available for sending"
                )
            result = signal_cli.send_group_message(
                resolved_group_id, message
            )
            result["resolved_name"] = chat_name
            _record_send(target_key)
            return result
        raise ValueError("No matching chat was found")

    return mcp
