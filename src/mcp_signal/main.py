from __future__ import annotations

import argparse
import hmac
import os
import sys
from typing import TYPE_CHECKING

from .server import build_server

if TYPE_CHECKING:
    from fastmcp.server.auth import AuthProvider


def _split_host_port(addr: str) -> tuple[str, int]:
    """Split a ``host:port`` listen address into its parts.

    IPv6 literals are not supported — the sidecar binds ``0.0.0.0``.
    """
    host, sep, port = addr.rpartition(":")
    if not sep or not host or not port:
        raise ValueError(f"invalid listen address {addr!r}; expected host:port")
    return host, int(port)


def _build_http_auth() -> AuthProvider | None:
    """Return a fastmcp auth provider enforcing a shared bearer token.

    When ``MCP_AUTH_TOKEN`` is set, requests to the streamable-HTTP MCP
    endpoint must carry ``Authorization: Bearer <token>``; fastmcp's auth
    pipeline only wraps that endpoint, so the ``/health`` probe (registered
    separately via ``custom_route``) stays unauthenticated. This mirrors the
    enforced-token posture of the other Den MCP sidecars (the daemon forwards
    the token it resolves from ``auth_token: env:SIGNAL_MCP_TOKEN``). With no
    token configured (local / stdio use) this returns None and no auth
    applies.
    """
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        return None

    from fastmcp.server.auth import AccessToken, TokenVerifier

    class _SharedTokenVerifier(TokenVerifier):
        async def verify_token(self, token_value: str) -> AccessToken | None:
            if not hmac.compare_digest(token_value, token):
                return None
            return AccessToken(
                token=token_value, client_id="den-daemon", scopes=[], expires_at=None
            )

    return _SharedTokenVerifier()


def _attach_health(mcp) -> None:
    """Add an unauthenticated ``GET /health`` returning 200 for probes."""
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(_request: Request) -> PlainTextResponse:  # noqa: ANN202
        return PlainTextResponse("ok")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signal-mcp")
    subparsers = parser.add_subparsers(dest="command")
    serve_parser = subparsers.add_parser(
        "serve", help="Run the MCP server (stdio by default, HTTP with --http)"
    )
    serve_parser.add_argument(
        "--http",
        action="store_true",
        help="Serve over streamable HTTP instead of stdio (also enabled by MCP_LISTEN_ADDR)",
    )
    serve_parser.add_argument(
        "--listen-addr",
        default=None,
        help="HTTP bind address host:port (default 0.0.0.0:8765, env MCP_LISTEN_ADDR)",
    )
    subparsers.add_parser("smoke", help="Construct the server and exit")

    args = parser.parse_args(argv)
    command = args.command or "serve"

    if command == "smoke":
        build_server()
        print("signal-mcp smoke: ok")
        return 0
    if command == "serve":
        http_mode = getattr(args, "http", False) or bool(
            os.environ.get("MCP_LISTEN_ADDR")
        )
        mcp = build_server()
        if http_mode:
            addr = (
                getattr(args, "listen_addr", None)
                or os.environ.get("MCP_LISTEN_ADDR")
                or "0.0.0.0:8765"
            )
            host, port = _split_host_port(addr)
            _attach_health(mcp)
            mcp.auth = _build_http_auth()
            # transport="http" is fastmcp's streamable-HTTP listener served
            # at /mcp, which the Den daemon's MCP connector dials over HTTPS.
            mcp.run(transport="http", host=host, port=port, path="/mcp")
        else:
            mcp.run()
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
