from __future__ import annotations

from mcp_signal.config import load_config


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
