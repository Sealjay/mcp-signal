from __future__ import annotations

from mcp_signal.config import SignalConfig


def make_config(**overrides) -> SignalConfig:
    defaults = {
        "source_dir": None,  # type: ignore[arg-type]
        "signal_cli_path": "/bin/echo",
        "signal_account": "+44123",
    }
    defaults.update(overrides)
    return SignalConfig(**defaults)
