from __future__ import annotations

import json
import subprocess

import pytest

from mcp_signal.config import SignalConfig
from mcp_signal.signal_cli import SignalCLIClient, SignalCLIError


def build_config() -> SignalConfig:
    return SignalConfig(
        source_dir=None,  # type: ignore[arg-type]
        signal_cli_path="/bin/echo",
        signal_account="+44123",
        signal_db_password=None,
        signal_db_key=None,
        jsonrpc_timeout_seconds=30,
    )


def runner_success(command, *, input, capture_output, text, timeout, check):
    del command, capture_output, text, timeout, check
    request = json.loads(input.strip())
    if request["method"] == "listGroups":
        payload = {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": [{"id": "group-1", "name": "Weekend Plans", "members": ["+44111"]}],
        }
    else:
        payload = {"jsonrpc": "2.0", "id": request["id"], "result": {"timestamp": 12345}}
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload) + "\n", stderr="")


def test_list_groups_filters_by_query():
    client = SignalCLIClient(build_config(), runner=runner_success)
    groups = client.list_groups(query="weekend")
    assert groups == [
        {
            "group_id": "group-1",
            "name": "Weekend Plans",
            "description": "",
            "members": ["+44111"],
            "admins": [],
            "is_member": True,
            "is_blocked": False,
        }
    ]


def test_send_direct_message_returns_timestamp():
    client = SignalCLIClient(build_config(), runner=runner_success)
    result = client.send_direct_message("+44111", "Hello")
    assert result["target_type"] == "direct"
    assert result["timestamp"] == 12345


def runner_error(command, *, input, capture_output, text, timeout, check):
    del command, input, capture_output, text, timeout, check
    return subprocess.CompletedProcess([], 1, stdout="", stderr="boom")


def test_rpc_raises_on_non_zero_exit():
    client = SignalCLIClient(build_config(), runner=runner_error)
    with pytest.raises(SignalCLIError, match="boom"):
        client.list_groups()
