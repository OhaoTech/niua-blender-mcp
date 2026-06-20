"""Thin CLI over BlenderBridge so non-Python agents can drive a live Blender.

Usage:
    python scripts/bridge_call.py <port> <tool> '<json-args>'

Prints the tool result as JSON on stdout, or {"error": {...}} with a non-zero exit
on a structured bridge error. Used by the Phase-B convergence workflow's agents to
attempt tasks against the running bridge.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from niua_blender_mcp.bridge import BlenderBridge, BridgeError  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(json.dumps({"error": "usage: bridge_call.py <port> <tool> '<json-args>'"}))
        return 2
    port = int(argv[1])
    tool = argv[2]
    args = json.loads(argv[3]) if len(argv) > 3 and argv[3].strip() else {}
    b = BlenderBridge(port=port, timeout=120.0)
    try:
        result = b.call(tool, args)
    except BridgeError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
