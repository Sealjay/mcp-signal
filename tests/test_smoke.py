from __future__ import annotations

import asyncio
import json
import subprocess

from mcp_signal.config import SignalConfig
from mcp_signal.server import build_server
from mcp_signal.signal_cli import SignalCLIClient


def test_build_server_smoke():
    server = build_server()
    assert server is not None


def test_server_exposes_core_tool_names():
    server = build_server()
    tool_names = {tool.name for tool in asyncio.run(server.list_tools())}
    expected = {
        "get_status",
        "list_chats",
        "read_messages",
        "search_messages",
        "list_groups",
        "chat_activity",
        "decrypt_attachment",
        "send_message",
    }
    assert expected.issubset(tool_names)
    legacy_aliases = {
        "signal_list_chats",
        "signal_read_messages",
        "signal_get_chat_messages",
        "signal_search_messages",
        "signal_search_chat",
        "signal_list_groups",
        "signal_get_status",
        "signal_send_message",
        "signal_chat_activity",
    }
    assert tool_names.isdisjoint(legacy_aliases)


# --- Global rate limit ---

def _make_send_config() -> SignalConfig:
    return SignalConfig(
        source_dir=None,  # type: ignore[arg-type]
        signal_cli_path="/bin/echo",
        signal_account="+44123",
        signal_db_password=None,
        signal_db_key=None,
        jsonrpc_timeout_seconds=30,
    )


def _runner_ok(command, *, input, capture_output, text, timeout, check):
    del command, capture_output, text, timeout, check
    request = json.loads(input.strip())
    payload = {"jsonrpc": "2.0", "id": request["id"], "result": {"timestamp": 99}}
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload) + "\n", stderr="")


def test_global_rate_limit_blocks_burst():
    """Sending more than _GLOBAL_SEND_BURST distinct messages raises a rate-limit error."""
    from mcp_signal.server import build_server

    cfg = _make_send_config()
    cli = SignalCLIClient(cfg, runner=_runner_ok)

    from unittest.mock import patch

    with patch("mcp_signal.server.SignalCLIClient", return_value=cli):
        server = build_server(config=cfg)

    # Each call uses a distinct recipient to bypass per-recipient cooldown.
    # After _GLOBAL_SEND_BURST (10) sends the server must block further sends.
    sent = 0
    blocked = False
    for i in range(15):
        number = f"+4411111{i:04d}"
        try:
            asyncio.run(
                server.call_tool("send_message", {"message": "hi", "phone_number": number})
            )
            sent += 1
        except Exception:
            blocked = True
            break

    assert blocked, "Expected the global rate limit to block the burst, but all 15 sends succeeded"
    assert sent == 10, f"Expected exactly 10 sends before the global limit; got {sent}"
