from __future__ import annotations

import argparse
import hmac
import os
import sys

from .server import build_server


def _split_host_port(addr: str) -> tuple[str, int]:
    """Split a ``host:port`` listen address into its parts.

    IPv6 literals are not supported — the sidecar binds ``0.0.0.0``.
    """
    host, sep, port = addr.rpartition(":")
    if not sep or not host or not port:
        raise ValueError(f"invalid listen address {addr!r}; expected host:port")
    return host, int(port)


def _build_http_middleware() -> list:
    """Return Starlette middleware enforcing a shared bearer token.

    When ``MCP_AUTH_TOKEN`` is set, every HTTP request except the
    unauthenticated ``/health`` probe must carry
    ``Authorization: Bearer <token>``. This mirrors the enforced-token
    posture of the other Den MCP sidecars (the daemon forwards the token
    it resolves from ``auth_token: env:SIGNAL_MCP_TOKEN``). With no token
    configured (local / stdio use) the list is empty and no auth applies.
    """
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        return []

    from starlette.middleware import Middleware
    from starlette.types import ASGIApp, Receive, Scope, Send

    class BearerAuthMiddleware:
        def __init__(self, app: ASGIApp, expected: str) -> None:
            self.app = app
            self.expected = expected

        async def __call__(
            self, scope: Scope, receive: Receive, send: Send
        ) -> None:
            if scope["type"] != "http" or scope.get("path") == "/health":
                await self.app(scope, receive, send)
                return
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode("latin-1")
            presented = auth[7:] if auth.startswith("Bearer ") else ""
            if not presented or not hmac.compare_digest(presented, self.expected):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"text/plain")],
                    }
                )
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
            await self.app(scope, receive, send)

    return [Middleware(BearerAuthMiddleware, expected=token)]


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
            # fastmcp forwards host/port/path/middleware to run_http_async;
            # transport="http" is fastmcp's streamable-HTTP listener served
            # at /mcp, which the Den daemon's MCP connector dials over HTTPS.
            mcp.run(
                transport="http",
                host=host,
                port=port,
                path="/mcp",
                middleware=_build_http_middleware(),
            )
        else:
            mcp.run()
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
