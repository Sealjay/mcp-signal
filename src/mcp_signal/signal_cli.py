from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from collections.abc import Callable
from typing import Any

from .config import _E164_RE, SignalConfig

_log = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"\+[1-9]\d{6,14}")
_STDERR_MAX_CHARS = 200


def _redact_stderr(raw: str) -> str:
    """Truncate and redact phone numbers from signal-cli stderr before logging."""
    truncated = raw[:_STDERR_MAX_CHARS]
    if len(raw) > _STDERR_MAX_CHARS:
        truncated += " [truncated]"
    return _PHONE_RE.sub("<phone_redacted>", truncated)


def _validate_phone_number(phone_number: str) -> None:
    if not _E164_RE.match(phone_number):
        raise SignalCLIError("Invalid phone number format; expected E.164 (e.g. +441234567890)")


class SignalCLIError(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess[str]]


class SignalCLIClient:
    def __init__(self, config: SignalConfig, runner: Runner | None = None) -> None:
        self._config = config
        self._runner = runner or subprocess.run

    def _ensure_send_ready(self) -> None:
        if not self._config.signal_cli_available:
            raise SignalCLIError(
                "signal-cli is not available; install it or set SIGNAL_CLI_PATH explicitly"
            )
        if not self._config.signal_account:
            raise SignalCLIError("SIGNAL_ACCOUNT is required for Signal send operations")

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._ensure_send_ready()
        request_id = uuid.uuid4().hex
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id,
        }
        if params:
            request["params"] = params
        proc = self._runner(
            [self._config.signal_cli_path, "-a", self._config.signal_account, "jsonRpc"],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            timeout=self._config.jsonrpc_timeout_seconds,
            check=False,
        )
        if proc.returncode != 0:
            _log.debug("signal-cli stderr: %s", _redact_stderr(proc.stderr.strip()))
            raise SignalCLIError("signal-cli exited with a non-zero status")
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                error = payload["error"]
                message = error.get("message") if isinstance(error, dict) else str(error)
                _log.debug("signal-cli RPC error: %s", message)
                raise SignalCLIError("signal-cli operation failed")
            return payload.get("result")
        raise SignalCLIError(f"signal-cli returned no response for method {method}")

    def list_groups(self, *, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        groups = self._rpc("listGroups") or []
        query_lower = query.strip().lower()
        rows = []
        for group in groups:
            name = group.get("name") or ""
            if query_lower and query_lower not in name.lower():
                continue
            rows.append(
                {
                    "group_id": group.get("id"),
                    "name": name,
                    "description": group.get("description") or "",
                    "members": group.get("members") or [],
                    "admins": group.get("admins") or [],
                    "is_member": group.get("isMember", True),
                    "is_blocked": group.get("isBlocked", False),
                }
            )
        rows.sort(key=lambda item: item["name"].lower())
        return rows[:limit]

    def find_group_matches(self, chat_name: str) -> list[dict[str, Any]]:
        target = chat_name.strip().casefold()
        return [
            group
            for group in self.list_groups(limit=10_000)
            if group["name"].strip().casefold() == target
        ]

    def send_direct_message(self, phone_number: str, message: str) -> dict[str, Any]:
        _validate_phone_number(phone_number)
        result = self._rpc("send", {"recipient": [phone_number], "message": message}) or {}
        return {
            "target_type": "direct",
            "target": phone_number,
            "timestamp": result.get("timestamp"),
        }

    def send_group_message(self, group_id: str, message: str) -> dict[str, Any]:
        result = self._rpc("send", {"groupId": group_id, "message": message}) or {}
        return {
            "target_type": "group",
            "target": group_id,
            "timestamp": result.get("timestamp"),
        }
