from __future__ import annotations

import argparse
import sys

from .server import build_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signal-mcp")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Run the stdio MCP server")
    subparsers.add_parser("smoke", help="Construct the server and exit")

    args = parser.parse_args(argv)
    command = args.command or "serve"

    if command == "smoke":
        build_server()
        print("signal-mcp smoke: ok")
        return 0
    if command == "serve":
        build_server().run()
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

