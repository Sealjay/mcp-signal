from __future__ import annotations

import warnings

import pytest

from mcp_signal.config import (
    _parse_timeout_seconds,
    _validate_signal_account,
    _validate_signal_cli_path,
    load_config,
)


def test_load_config_reads_dotenv_local(tmp_path, monkeypatch):
    data_dir = tmp_path / "signal-data"
    data_dir.mkdir()
    (tmp_path / ".env.local").write_text(
        'SIGNAL_ACCOUNT="+441234567890"\nSIGNAL_CLI_PATH=/bin/echo\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SIGNAL_ACCOUNT", raising=False)
    monkeypatch.delenv("SIGNAL_CLI_PATH", raising=False)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(data_dir))

    config = load_config()

    assert config.signal_account == "+441234567890"
    assert config.signal_cli_path == "/bin/echo"
    assert config.source_dir == data_dir


# --- SIGNAL_ACCOUNT validation ---

def test_validate_signal_account_accepts_e164():
    assert _validate_signal_account("+441234567890") == "+441234567890"


@pytest.mark.parametrize("bad", ["not-a-phone", "441234567890", "+1", ""])
def test_validate_signal_account_rejects_invalid(bad):
    with pytest.raises(ValueError, match="E.164"):
        _validate_signal_account(bad)


def test_load_config_rejects_bad_account(tmp_path, monkeypatch):
    data_dir = tmp_path / "signal-data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SIGNAL_ACCOUNT", "not-a-phone")
    monkeypatch.delenv("SIGNAL_CLI_PATH", raising=False)
    with pytest.raises(ValueError, match="E.164"):
        load_config()


# --- SIGNAL_CLI_PATH validation ---

def test_validate_signal_cli_path_accepts_safe_paths():
    assert _validate_signal_cli_path("signal-cli") == "signal-cli"
    assert _validate_signal_cli_path("/usr/local/bin/signal-cli") == "/usr/local/bin/signal-cli"


@pytest.mark.parametrize("bad", ["signal; rm -rf /", "signal|whoami", "$(evil)", ""])
def test_validate_signal_cli_path_rejects_metacharacters(bad):
    with pytest.raises(ValueError):
        _validate_signal_cli_path(bad)


def test_load_config_rejects_bad_cli_path(tmp_path, monkeypatch):
    data_dir = tmp_path / "signal-data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(data_dir))
    monkeypatch.delenv("SIGNAL_ACCOUNT", raising=False)
    monkeypatch.setenv("SIGNAL_CLI_PATH", "signal; rm -rf /")
    with pytest.raises(ValueError, match="unsafe characters"):
        load_config()


# --- SIGNAL_JSONRPC_TIMEOUT_SECONDS ---

def test_parse_timeout_seconds_valid():
    assert _parse_timeout_seconds("60") == 60


def test_parse_timeout_seconds_invalid_falls_back():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _parse_timeout_seconds("not-a-number", default=30)
    assert result == 30
    assert any("not-a-number" in str(warning.message) for warning in w)


def test_load_config_bad_timeout_uses_default(tmp_path, monkeypatch):
    data_dir = tmp_path / "signal-data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(data_dir))
    monkeypatch.delenv("SIGNAL_ACCOUNT", raising=False)
    monkeypatch.delenv("SIGNAL_CLI_PATH", raising=False)
    monkeypatch.setenv("SIGNAL_JSONRPC_TIMEOUT_SECONDS", "banana")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        config = load_config()
    assert config.jsonrpc_timeout_seconds == 30
    assert any("banana" in str(warning.message) for warning in w)


def test_load_config_caps_timeout_at_300(tmp_path, monkeypatch):
    data_dir = tmp_path / "signal-data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGNAL_DATA_DIR", str(data_dir))
    monkeypatch.delenv("SIGNAL_ACCOUNT", raising=False)
    monkeypatch.delenv("SIGNAL_CLI_PATH", raising=False)
    monkeypatch.setenv("SIGNAL_JSONRPC_TIMEOUT_SECONDS", "9999")
    config = load_config()
    assert config.jsonrpc_timeout_seconds == 300
