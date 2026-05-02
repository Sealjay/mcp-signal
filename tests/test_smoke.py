from __future__ import annotations

from mcp_signal.server import build_server


def test_build_server_smoke():
    server = build_server()
    assert server is not None
