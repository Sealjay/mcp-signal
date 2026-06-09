from __future__ import annotations

import logging
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import SignalConfig

_log = logging.getLogger(__name__)

# The pairing URI signal-cli prints on stdout while `link` waits for a scan.
_LINK_URI_RE = re.compile(r"(sgnl://linkdevice\?[^\s]+)")
# A phone number, used to label the linked account from `listAccounts` output.
_PHONE_RE = re.compile(r"\+[1-9]\d{6,14}")

_DEVICE_NAME = "Den"
# The linked-state probe must stay fast so the handler never blocks; the link
# itself runs off-thread.
_LIST_ACCOUNTS_TIMEOUT_SECONDS = 5

_GENERATING_DETAIL = "Generating pairing link…"
_AWAITING_DETAIL = "Scan in Signal → Settings → Linked devices → Link new device"

Runner = Callable[..., subprocess.CompletedProcess[str]]
Popen = Callable[..., subprocess.Popen[str]]


def _error_state(detail: str) -> dict[str, Any]:
    return {"type": "setup_state", "state": "error", "detail": detail}


@dataclass(frozen=True)
class _LinkSnapshot:
    """Immutable view of the device-linking state, shared across threads."""

    state: str
    detail: str
    qr_payload: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": "setup_state",
            "state": self.state,
            "detail": self.detail,
        }
        if self.qr_payload is not None:
            result["qr_payload"] = self.qr_payload
        return result


class LinkManager:
    """Non-blocking state machine for the signal-cli device-linking flow.

    ``signal-cli link`` blocks until the phone scans the QR (which can take
    minutes), so the handler must never call it inline. The first
    ``pairing_status`` on an unlinked device spawns ``signal-cli link`` on a
    daemon thread, captures the ``sgnl://linkdevice`` URI from its stdout into a
    lock-protected snapshot, and leaves the process running. Subsequent calls
    return the cached snapshot until the linked-state probe (``listAccounts``)
    reports the account, at which point the state becomes ``ready``.
    """

    def __init__(
        self,
        config: SignalConfig,
        runner: Runner | None = None,
        popen: Popen | None = None,
    ) -> None:
        self._config = config
        self._runner = runner or subprocess.run
        self._popen = popen or subprocess.Popen
        self._lock = threading.Lock()
        self._link_in_progress = False
        self._thread: threading.Thread | None = None
        self._snapshot = _LinkSnapshot(state="awaiting_qr", detail=_GENERATING_DETAIL)

    def pairing_status(self) -> dict[str, Any]:
        """Return the current setup_state envelope without ever blocking."""
        try:
            if not self._config.signal_cli_available:
                return _error_state("signal-cli is not available")

            account = self._check_already_linked()
            if account is not None:
                snapshot = _LinkSnapshot(state="ready", detail=f"Linked to {account}")
                with self._lock:
                    self._snapshot = snapshot
                    self._link_in_progress = False
                return snapshot.to_dict()

            with self._lock:
                if self._link_in_progress:
                    return self._snapshot.to_dict()
                # Start a fresh background link attempt.
                self._link_in_progress = True
                self._snapshot = _LinkSnapshot(state="awaiting_qr", detail=_GENERATING_DETAIL)
                snapshot = self._snapshot

            self._start_link_thread()
            return snapshot.to_dict()
        except Exception as exc:  # never raise out of the handler
            _log.debug("pairing_status failed: %s", exc)
            return _error_state(str(exc) or "unexpected error during Signal pairing")

    def _check_already_linked(self) -> str | None:
        """Return the linked account label, or None if no account is linked."""
        try:
            proc = self._runner(
                [self._config.signal_cli_path, "listAccounts"],
                capture_output=True,
                text=True,
                timeout=_LIST_ACCOUNTS_TIMEOUT_SECONDS,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            _log.debug("listAccounts probe failed: %s", exc)
            return None
        if proc.returncode != 0:
            return None
        output = (proc.stdout or "").strip()
        if not output:
            return None
        match = _PHONE_RE.search(output)
        if match is not None:
            return match.group(0)
        return self._config.signal_account or "this device"

    def _start_link_thread(self) -> None:
        _log.info("starting Signal device link")
        thread = threading.Thread(
            target=self._run_link_background, name="signal-link", daemon=True
        )
        self._thread = thread
        thread.start()

    def _run_link_background(self) -> None:
        """Thread target: run ``signal-cli link`` and track its progress."""
        try:
            proc = self._popen(
                [self._config.signal_cli_path, "link", "-n", _DEVICE_NAME],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception as exc:
            _log.warning("failed to start Signal device link: %s", exc)
            with self._lock:
                self._snapshot = _LinkSnapshot(
                    state="error",
                    detail=str(exc) or "could not start Signal device link",
                )
                self._link_in_progress = False
            return

        returncode = 1
        try:
            if proc.stdout is not None:
                for raw_line in proc.stdout:
                    uri = self._read_link_uri(raw_line)
                    if uri is None:
                        continue
                    _log.info("captured Signal pairing URI")
                    with self._lock:
                        self._snapshot = _LinkSnapshot(
                            state="awaiting_qr",
                            detail=_AWAITING_DETAIL,
                            qr_payload=uri,
                        )
            returncode = proc.wait()
        except Exception as exc:
            _log.warning("Signal device link reading failed: %s", exc)
            with self._lock:
                self._snapshot = _LinkSnapshot(
                    state="error", detail=str(exc) or "Signal device link failed"
                )
                self._link_in_progress = False
            return

        if returncode == 0:
            account = self._check_already_linked()
            _log.info("Signal device link completed")
            with self._lock:
                self._snapshot = _LinkSnapshot(
                    state="ready", detail=f"Linked to {account or 'this device'}"
                )
                self._link_in_progress = False
        else:
            _log.warning("Signal device link exited with status %s", returncode)
            with self._lock:
                self._snapshot = _LinkSnapshot(
                    state="error", detail="Signal device link did not complete"
                )
                self._link_in_progress = False

    def _read_link_uri(self, line: str) -> str | None:
        match = _LINK_URI_RE.search(line)
        return match.group(1) if match else None
