"""stdio entry point: one JSON-RPC message per line in, one per line out."""

from __future__ import annotations

import argparse
import json
import sys

from .bridge import BlenderBridge
from .protocol import PARSE_ERROR, error_response
from .server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Niua Blender MCP stdio server.")
    parser.add_argument("--host", default="127.0.0.1", help="Blender bridge host")
    parser.add_argument("--port", default=8765, type=int, help="Blender bridge port")
    parser.add_argument("--timeout", default=30.0, type=float, help="Bridge timeout (seconds)")
    parser.add_argument("--allow-python", action="store_true", help="Enable system.execute_python")
    return parser


def run_stdio(server) -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = server.handle(json.loads(line))
        except json.JSONDecodeError as exc:
            response = error_response(None, PARSE_ERROR, f"Invalid JSON: {exc}")
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bridge = BlenderBridge(host=args.host, port=args.port, timeout=args.timeout)
    server = create_server(bridge=bridge, allow_python=args.allow_python or None)
    return run_stdio(server)


if __name__ == "__main__":
    raise SystemExit(main())
