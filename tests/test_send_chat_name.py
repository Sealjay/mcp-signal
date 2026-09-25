from __future__ import annotations

import asyncio
import json
import subprocess
from unittest.mock import patch

import pytest
from conftest import make_config
from fastmcp.exceptions import ToolError

from mcp_signal.server import build_server
from mcp_signal.signal_cli import SignalCLIClient

ACI = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def _server(direct_chats, *, list_groups_fails=False):
    """Build a server with a fake Desktop reader and a recording signal-cli runner."""
    calls: list[dict] = []

    def runner(command, *, input, capture_output, text, timeout, check):
        request = json.loads(input.strip())
        calls.append(request)
        if request["method"] == "listGroups":
            if list_groups_fails:
                return subprocess.CompletedProcess([], 1, stdout="", stderr="locked")
            result = []
        else:
            result = {"timestamp": 1}
        payload = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload) + "\n", stderr="")

    cfg = make_config()
    cli = SignalCLIClient(cfg, runner=runner)
    with (
        patch("mcp_signal.server.SignalCLIClient", return_value=cli),
        patch("mcp_signal.server.DesktopReader") as reader_cls,
    ):
        reader_cls.return_value.find_direct_chat_matches.return_value = direct_chats
        server = build_server(config=cfg)
    return server, calls


def _send(server, chat_name):
    return asyncio.run(server.call_tool("send_message", {"message": "hi", "chat_name": chat_name}))


def _sent_recipients(calls):
    return [c["params"]["recipient"] for c in calls if c["method"] == "send"]


def test_chat_name_with_hidden_number_sends_to_service_id():
    server, calls = _server([{"name": "Alex", "number": "", "service_id": ACI}])
    _send(server, "Alex")
    assert _sent_recipients(calls) == [[ACI]]


def test_chat_name_direct_send_survives_list_groups_failure():
    server, calls = _server(
        [{"name": "Alex", "number": "+441234567890", "service_id": ACI}],
        list_groups_fails=True,
    )
    _send(server, "Alex")
    assert _sent_recipients(calls) == [["+441234567890"]]


def test_chat_name_errors_are_not_masked():
    server, _ = _server([])
    with pytest.raises(ToolError, match="No matching chat was found"):
        _send(server, "Nobody")
