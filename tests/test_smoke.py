from __future__ import annotations

import asyncio

from mcp_signal.server import build_server


def test_build_server_smoke():
    server = build_server()
    assert server is not None


def test_server_exposes_legacy_signal_tool_names():
    server = build_server()
    tool_names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert "signal_list_chats" in tool_names
    assert "signal_get_chat_messages" in tool_names
    assert "signal_chat_activity" in tool_names
    assert "signal_send_message" in tool_names
