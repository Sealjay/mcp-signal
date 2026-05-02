from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path


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
    signal_db_password: str | None
    signal_db_key: str | None
    jsonrpc_timeout_seconds: int

    @property
    def signal_cli_available(self) -> bool:
        if os.path.sep in self.signal_cli_path:
            return Path(self.signal_cli_path).exists()
        return shutil.which(self.signal_cli_path) is not None


def load_config() -> SignalConfig:
    source_dir = Path(os.getenv("SIGNAL_DATA_DIR", default_signal_dir()))
    return SignalConfig(
        source_dir=source_dir,
        signal_cli_path=os.getenv("SIGNAL_CLI_PATH", "signal-cli"),
        signal_account=os.getenv("SIGNAL_ACCOUNT"),
        signal_db_password=os.getenv("SIGNAL_DB_PASSWORD"),
        signal_db_key=os.getenv("SIGNAL_DB_KEY"),
        jsonrpc_timeout_seconds=int(os.getenv("SIGNAL_JSONRPC_TIMEOUT_SECONDS", "30")),
    )

