from __future__ import annotations

import os
import platform
import re
import shutil
import warnings
from dataclasses import dataclass, field
from pathlib import Path

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
# Allowlist: word chars, hyphens, dots, slashes, spaces — no shell metacharacters.
_CLI_PATH_SAFE_RE = re.compile(r"^[\w\-./\\ ]+$")


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _validate_signal_account(value: str) -> str:
    """Validate SIGNAL_ACCOUNT is a valid E.164 phone number."""
    if not _E164_RE.match(value):
        raise ValueError(
            f"SIGNAL_ACCOUNT must be an E.164 phone number (e.g. +441234567890); got: {value!r}"
        )
    return value


def _validate_signal_cli_path(value: str) -> str:
    """Validate SIGNAL_CLI_PATH contains no shell metacharacters."""
    if not value:
        raise ValueError("SIGNAL_CLI_PATH must not be empty")
    if not _CLI_PATH_SAFE_RE.match(value):
        raise ValueError(
            "SIGNAL_CLI_PATH contains unsafe characters; only word chars, hyphens, "
            f"dots, slashes, and spaces are allowed; got: {value!r}"
        )
    return value


def _parse_timeout_seconds(raw: str, default: int = 30) -> int:
    """Parse SIGNAL_JSONRPC_TIMEOUT_SECONDS safely, falling back to *default* on error."""
    try:
        return int(raw)
    except (ValueError, TypeError):
        warnings.warn(
            f"SIGNAL_JSONRPC_TIMEOUT_SECONDS={raw!r} is not a valid integer; "
            f"using default {default}",
            stacklevel=3,
        )
        return default


def load_local_env(env_file: str = ".env.local") -> None:
    env_path = Path.cwd() / env_file
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.startswith("SIGNAL_"):
            continue
        os.environ.setdefault(key, _strip_optional_quotes(value.strip()))


def default_signal_dir() -> Path:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return home / "AppData" / "Roaming" / "Signal"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Signal"
    if system == "Linux":
        flatpak = home / ".var" / "app" / "org.signal.Signal" / "config" / "Signal"
        return flatpak if flatpak.exists() else home / ".config" / "Signal"
    raise RuntimeError(f"Unsupported OS: {system}")


@dataclass(frozen=True)
class SignalConfig:
    source_dir: Path
    signal_cli_path: str
    signal_account: str | None
    signal_db_password: str | None = field(default=None, repr=False)
    signal_db_key: str | None = field(default=None, repr=False)
    jsonrpc_timeout_seconds: int = 30

    @property
    def signal_cli_available(self) -> bool:
        if os.path.sep in self.signal_cli_path:
            return Path(self.signal_cli_path).exists()
        return shutil.which(self.signal_cli_path) is not None


def load_config() -> SignalConfig:
    load_local_env()
    source_dir = Path(os.getenv("SIGNAL_DATA_DIR", default_signal_dir()))

    raw_account = os.getenv("SIGNAL_ACCOUNT")
    signal_account: str | None = None
    if raw_account:
        signal_account = _validate_signal_account(raw_account)

    raw_cli_path = os.getenv("SIGNAL_CLI_PATH", "signal-cli")
    signal_cli_path = _validate_signal_cli_path(raw_cli_path)

    raw_timeout = os.getenv("SIGNAL_JSONRPC_TIMEOUT_SECONDS", "30")
    timeout = _parse_timeout_seconds(raw_timeout)

    return SignalConfig(
        source_dir=source_dir,
        signal_cli_path=signal_cli_path,
        signal_account=signal_account,
        signal_db_password=os.getenv("SIGNAL_DB_PASSWORD"),
        signal_db_key=os.getenv("SIGNAL_DB_KEY"),
        jsonrpc_timeout_seconds=min(timeout, 300),
    )
