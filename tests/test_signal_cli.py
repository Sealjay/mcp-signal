from __future__ import annotations

import json
import subprocess

import pytest

from mcp_signal.config import SignalConfig
from mcp_signal.signal_cli import SignalCLIClient, SignalCLIError, _redact_stderr


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
    result = client.send_direct_message("+441234567890", "Hello")
    assert result["target_type"] == "direct"
    assert result["timestamp"] == 12345


def runner_error(command, *, input, capture_output, text, timeout, check):
    del command, input, capture_output, text, timeout, check
    return subprocess.CompletedProcess([], 1, stdout="", stderr="boom")


def test_rpc_raises_on_non_zero_exit():
    client = SignalCLIClient(build_config(), runner=runner_error)
    with pytest.raises(SignalCLIError, match="signal-cli exited with a non-zero status"):
        client.list_groups()


# --- stderr redaction ---

def test_redact_stderr_removes_phone_numbers():
    raw = "Error sending to +441234567890: connection refused"
    result = _redact_stderr(raw)
    assert "+441234567890" not in result
    assert "<phone_redacted>" in result


def test_redact_stderr_truncates_long_output():
    long = "x" * 500
    result = _redact_stderr(long)
    assert len(result) <= 220  # 200 chars + "[truncated]"
    assert "[truncated]" in result


def test_redact_stderr_preserves_short_benign_output():
    msg = "timeout waiting for response"
    assert _redact_stderr(msg) == msg


def runner_error_with_phone(command, *, input, capture_output, text, timeout, check):
    del command, input, capture_output, text, timeout, check
    return subprocess.CompletedProcess(
        [], 1, stdout="", stderr="Failed for account +441234567890 bad token"
    )


def test_rpc_stderr_is_redacted_in_log(caplog):
    import logging
    client = SignalCLIClient(build_config(), runner=runner_error_with_phone)
    with caplog.at_level(logging.DEBUG, logger="mcp_signal.signal_cli"):
        with pytest.raises(SignalCLIError):
            client.list_groups()
    log_text = " ".join(caplog.messages)
    assert "+441234567890" not in log_text
    assert "<phone_redacted>" in log_text
