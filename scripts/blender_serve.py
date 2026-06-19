"""Headless bridge launcher: run inside Blender via

    blender --background --factory-startup --python scripts/blender_serve.py -- \
        <addon_dir> <port> <allow_python 0|1> <idle_timeout_seconds>

Adds the add-on directory to sys.path, then runs the main-thread drain loop until
idle. Used by the headless smoke test and by any headless worker deployment.
"""

import sys

argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else []
addon_dir = args[0]
port = int(args[1])
allow_python = args[2] == "1"
idle_timeout = float(args[3]) if len(args) > 3 else 30.0

sys.path.insert(0, addon_dir)

from niua_mcp_bridge import bridge_server  # noqa: E402

print(f"[niua] headless bridge starting on 127.0.0.1:{port} (idle_timeout={idle_timeout}s)", flush=True)
bridge_server.serve_blocking(port=port, allow_python=allow_python, idle_timeout=idle_timeout)
print("[niua] headless bridge stopped", flush=True)
