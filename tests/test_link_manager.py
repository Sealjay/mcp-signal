from __future__ import annotations

import subprocess
import threading
import time

from mcp_signal.config import SignalConfig
from mcp_signal.link_manager import LinkManager

_LINK_URI = "sgnl://linkdevice?uuid=abc123&pub_key=Zm9vYmFy"


def _config(signal_cli_path: str = "/bin/echo") -> SignalConfig:
    return SignalConfig(
        source_dir=None,  # type: ignore[arg-type]
        signal_cli_path=signal_cli_path,
        signal_account="+44123",
        signal_db_password=None,
        signal_db_key=None,
        jsonrpc_timeout_seconds=30,
    )


def _accounts_runner(stdout: str):
    def runner(command, *, capture_output, text, timeout, check):
        del command, capture_output, text, timeout, check
        return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")

    return runner


def test_pairing_status_signal_cli_missing_returns_error():
    manager = LinkManager(_config(signal_cli_path="/no/such/signal-cli"))
    result = manager.pairing_status()
    assert result == {
        "type": "setup_state",
        "state": "error",
        "detail": "signal-cli is not available",
    }


def test_pairing_status_already_linked_returns_ready():
    runner = _accounts_runner("Number: +447700900123\n")
    manager = LinkManager(_config(), runner=runner)
    result = manager.pairing_status()
    assert result == {
        "type": "setup_state",
        "state": "ready",
        "detail": "Linked to +447700900123",
    }


class _FakeLinkProc:
    """A signal-cli link stand-in that emits the URI then blocks like a real one."""

    def __init__(self, lines: list[str], release: threading.Event) -> None:
        self._release = release
        self.stdout = self._generate(lines)

    def _generate(self, lines: list[str]):
        yield from lines
        # Mimic `signal-cli link` blocking on the phone scan: hold the stream
        # open so the process does not exit and overwrite awaiting_qr.
        self._release.wait(timeout=5)

    def wait(self) -> int:
        self._release.wait(timeout=5)
        return 0


def test_pairing_status_captures_uri_into_awaiting_qr():
    release = threading.Event()
    fake_proc = _FakeLinkProc([f"{_LINK_URI}\n"], release)

    def popen(command, *, stdout, stderr, text):
        del command, stdout, stderr, text
        return fake_proc

    # listAccounts always reports unlinked so the link flow runs.
    manager = LinkManager(_config(), runner=_accounts_runner(""), popen=popen)

    # First call: no link in progress, so it starts one and reports generating.
    first = manager.pairing_status()
    assert first == {
        "type": "setup_state",
        "state": "awaiting_qr",
        "detail": "Generating pairing link…",
    }

    try:
        # Poll until the background thread captures the URI.
        result: dict | None = None
        for _ in range(100):
            result = manager.pairing_status()
            if result.get("qr_payload"):
                break
            time.sleep(0.02)

        assert result == {
            "type": "setup_state",
            "state": "awaiting_qr",
            "detail": "Scan in Signal → Settings → Linked devices → Link new device",
            "qr_payload": _LINK_URI,
        }
    finally:
        release.set()
