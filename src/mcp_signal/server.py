from __future__ import annotations

import time
from typing import Any

from fastmcp import FastMCP

from .config import SignalConfig, load_config
from .reader import DesktopReader
from .signal_cli import SignalCLIClient, SignalCLIError

_MAX_LIMIT = 200
_MAX_OFFSET = 10_000


def build_server(config: SignalConfig | None = None) -> FastMCP:
    cfg = config or load_config()
    reader = DesktopReader(cfg)
    signal_cli = SignalCLIClient(cfg)

    _last_send_times: dict[str, float] = {}
    _SEND_COOLDOWN_SECONDS = 1.0

    mcp = FastMCP(
        "Signal MCP Server",
        version="0.1.2",
        strict_input_validation=True,
        mask_error_details=True,
    )

    @mcp.tool()
    def list_chats(query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """List direct and group Signal chats from the local desktop database."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        return reader.list_chats(query=query, limit=limit)

    @mcp.tool()
    def read_messages(
        chat_name: str,
        limit: int = 20,
        offset: int = 0,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read messages from one Signal chat by exact chat name."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        offset = min(max(offset, 0), _MAX_OFFSET)
        return reader.read_messages(
            chat_name,
            limit=limit,
            offset=offset,
            after=after,
            before=before,
        )

    @mcp.tool()
    def search_messages(
        query: str,
        chat_name: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search Signal messages within one chat or across all chats."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        return reader.search_messages(query=query, chat_name=chat_name, limit=limit)

    @mcp.tool()
    def list_groups(query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """List Signal groups with group IDs when signal-cli is configured."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        try:
            return signal_cli.list_groups(query=query, limit=limit)
        except SignalCLIError:
            return reader.list_local_groups(query=query, limit=limit)

    @mcp.tool()
    def get_status() -> dict[str, Any]:
        """Return readiness for local reads and outbound sends."""
        return {
            "source_dir_exists": cfg.source_dir.exists(),
            "signal_cli_available": cfg.signal_cli_available,
            "signal_account_configured": bool(cfg.signal_account),
            "read_available": cfg.source_dir.exists(),
            "send_available": cfg.signal_cli_available and bool(cfg.signal_account),
        }

    @mcp.tool()
    def signal_list_chats(query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Compatibility alias for daiclaw/lifeos Signal chat listing."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        return list_chats(query=query, limit=limit)

    @mcp.tool()
    def signal_read_messages(
        chat_name: str,
        limit: int = 20,
        offset: int = 0,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        """Compatibility alias for reading messages by exact chat name."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        offset = min(max(offset, 0), _MAX_OFFSET)
        return read_messages(
            chat_name=chat_name,
            limit=limit,
            offset=offset,
            after=after,
            before=before,
        )

    @mcp.tool()
    def signal_get_chat_messages(
        chat_name: str,
        limit: int = 20,
        offset: int = 0,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        """Legacy compatibility alias used by existing daiclaw/lifeos flows."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        offset = min(max(offset, 0), _MAX_OFFSET)
        return read_messages(
            chat_name=chat_name,
            limit=limit,
            offset=offset,
            after=after,
            before=before,
        )

    @mcp.tool()
    def signal_search_messages(
        query: str,
        chat_name: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Compatibility alias for Signal message search."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        return search_messages(query=query, chat_name=chat_name, limit=limit)

    @mcp.tool()
    def signal_search_chat(
        chat_name: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Legacy compatibility alias for chat-scoped Signal search."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        return search_messages(query=query, chat_name=chat_name, limit=limit)

    @mcp.tool()
    def signal_list_groups(query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Compatibility alias for Signal group listing."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        return list_groups(query=query, limit=limit)

    @mcp.tool()
    def signal_chat_activity(limit: int = 50) -> list[dict[str, Any]]:
        """Legacy compatibility alias exposing unread-like chat activity state."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        return reader.chat_activity(limit=limit)

    @mcp.tool()
    def signal_get_status() -> dict[str, Any]:
        """Compatibility alias for Signal readiness status."""
        return get_status()

    @mcp.tool()
    def send_message(
        message: str,
        phone_number: str | None = None,
        group_id: str | None = None,
        chat_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a Signal message to a direct recipient or group.

        Exactly one of phone_number, group_id, or chat_name must be supplied.
        """
        provided = [
            value is not None and value != ""
            for value in (phone_number, group_id, chat_name)
        ]
        if sum(provided) != 1:
            raise ValueError("Provide exactly one of phone_number, group_id, or chat_name")

        target_key = phone_number or group_id or chat_name or ""
        now = time.monotonic()
        last = _last_send_times.get(target_key, 0.0)
        if now - last < _SEND_COOLDOWN_SECONDS:
            raise ValueError(
                "Rate limit: please wait before sending another message to the same recipient"
            )

        if phone_number:
            result = signal_cli.send_direct_message(phone_number, message)
            _last_send_times[target_key] = time.monotonic()
            return result
        if group_id:
            result = signal_cli.send_group_message(group_id, message)
            _last_send_times[target_key] = time.monotonic()
            return result
        assert chat_name is not None

        direct_matches = reader.find_direct_chat_matches(chat_name)
        group_matches = signal_cli.find_group_matches(chat_name)

        if direct_matches and group_matches:
            raise ValueError(
                "Ambiguous chat name; specify phone_number or group_id explicitly"
            )
        if len(direct_matches) > 1:
            raise ValueError(
                "Multiple direct chats matched; specify phone_number explicitly"
            )
        if len(group_matches) > 1:
            raise ValueError(
                "Multiple groups matched; specify group_id explicitly"
            )
        if len(direct_matches) == 1:
            number = direct_matches[0].get("number")
            if not number:
                raise ValueError("Matched chat has no phone number available for sending")
            result = signal_cli.send_direct_message(number, message)
            result["resolved_name"] = chat_name
            _last_send_times[target_key] = time.monotonic()
            return result
        if len(group_matches) == 1:
            resolved_group_id = group_matches[0].get("group_id")
            if not resolved_group_id:
                raise ValueError("Matched group has no group_id available for sending")
            result = signal_cli.send_group_message(resolved_group_id, message)
            result["resolved_name"] = chat_name
            _last_send_times[target_key] = time.monotonic()
            return result
        raise ValueError("No matching chat was found")

    @mcp.tool()
    def signal_send_message(
        message: str,
        phone_number: str | None = None,
        group_id: str | None = None,
        chat_name: str | None = None,
    ) -> dict[str, Any]:
        """Compatibility alias for outbound Signal text messages."""
        return send_message(
            message=message,
            phone_number=phone_number,
            group_id=group_id,
            chat_name=chat_name,
        )

    return mcp
