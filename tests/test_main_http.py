"""serve --http must run fastmcp statelessly (MCP 2026-07-28, no Mcp-Session-Id)."""

from __future__ import annotations

from mcp_signal import main as main_mod


class _FakeServer:
    def __init__(self) -> None:
        self.run_kwargs: dict | None = None
        self.auth = None

    def custom_route(self, *_args, **_kwargs):
        return lambda fn: fn

    def run(self, **kwargs) -> None:
        self.run_kwargs = kwargs


def test_http_serve_is_stateless(monkeypatch) -> None:
    fake = _FakeServer()
    monkeypatch.setattr(main_mod, "build_server", lambda: fake)
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    assert main_mod.main(["serve", "--http", "--listen-addr", "127.0.0.1:9"]) == 0
    assert fake.run_kwargs == {
        "transport": "http",
        "host": "127.0.0.1",
        "port": 9,
        "path": "/mcp",
        "stateless_http": True,
    }
