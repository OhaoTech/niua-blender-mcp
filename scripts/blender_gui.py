"""Dev launcher for a VISIBLE Blender with the bridge auto-started (no manual N-panel).

    blender --python scripts/blender_gui.py -- <addon_dir> <port> [allow_python 0|1]

Adds the add-on to sys.path, registers it (so the Niua N-panel appears), and starts
the bridge. bpy.app.timers drains requests on the main thread while you watch the
window. Useful for dogfooding without installing the add-on into Blender's prefs.
"""

import sys

argv = sys.argv
args = argv[argv.index("--") + 1:] if "--" in argv else []
addon_dir = args[0]
port = int(args[1]) if len(args) > 1 else 8765
allow_python = len(args) > 2 and args[2] == "1"

sys.path.insert(0, addon_dir)

import niua_mcp_bridge  # noqa: E402
from niua_mcp_bridge import bridge_server  # noqa: E402

niua_mcp_bridge.register()  # registers the Niua N-panel + operators
bridge_server.start(port=port, allow_python=allow_python)
print(f"[niua] GUI bridge listening on 127.0.0.1:{port}", flush=True)
