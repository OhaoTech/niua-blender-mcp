"""stdio entry point: one JSON-RPC message per line in, one per line out."""

from __future__ import annotations

import argparse
import io
import json
import sys
from typing import TextIO

from .bridge import BlenderBridge
from .protocol import PARSE_ERROR, error_response
from .server import create_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Niua Blender Finisher stdio server.")
    parser.add_argument("--host", default="127.0.0.1", help="Blender bridge host")
    parser.add_argument("--port", default=8765, type=int, help="Blender bridge port")
    parser.add_argument("--timeout", default=30.0, type=float, help="Bridge timeout (seconds)")
    parser.add_argument("--allow-python", action="store_true", help="Enable system.execute_python")
    return parser


def _utf8_stdio() -> tuple[TextIO, TextIO]:
    """Re-wrap stdio as UTF-8 text over the binary buffers.

    Windows text-mode encoding for redirected pipes is host-dependent (often
    cp1252) and can corrupt JSON-RPC. The official MCP Python SDK does the same
    re-wrap; we stay dependency-free but match that behavior.
    """
    stdin: TextIO
    stdout: TextIO
    if hasattr(sys.stdin, "buffer"):
        stdin = io.TextIOWrapper(
            sys.stdin.buffer,
            encoding="utf-8",
            errors="replace",
            newline="\n",
            line_buffering=True,
        )
    else:  # pragma: no cover
        stdin = sys.stdin
    if hasattr(sys.stdout, "buffer"):
        stdout = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
            newline="\n",
            write_through=True,
        )
    else:  # pragma: no cover
        stdout = sys.stdout
    return stdin, stdout


def run_stdio(server) -> int:
    stdin, stdout = _utf8_stdio()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        # Some hosts (or proxies) may still prefix an LSP-style header line; skip
        # non-JSON frames so Windows/Linux clients both survive.
        if not line.startswith("{"):
            continue
        try:
            response = server.handle(json.loads(line))
        except json.JSONDecodeError as exc:
            response = error_response(None, PARSE_ERROR, f"Invalid JSON: {exc}")
        if response is not None:
            stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False) + "\n")
            stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bridge = BlenderBridge(host=args.host, port=args.port, timeout=args.timeout)
    server = create_server(bridge=bridge, allow_python=args.allow_python or None)
    return run_stdio(server)


if __name__ == "__main__":
    raise SystemExit(main())
