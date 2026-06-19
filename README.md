# niua Blender MCP

An **agentic Blender**: a Model Context Protocol server that drives a live, visible
Blender the way a technical artist does. Built on a small kernel + pluggable domain
packs, with an RNA-introspection engine so coverage isn't capped by hand-written tools.

Standalone and decoupled from niua (it just reads/writes asset files). See
[`docs/DESIGN.md`](docs/DESIGN.md) for the full architecture and
[`docs/PLAN.md`](docs/PLAN.md) for the build plan.

## Layout

```
src/niua_blender_mcp/      MCP server (Python, stdio)
  kernel/                  ToolSpec contract, validation, errors, router
  domains/                 server-side tool manifest
  bridge.py                TCP client to the add-on
  server.py, __main__.py   MCP server + stdio entry
blender_addon/niua_mcp_bridge/   the in-Blender half (Python add-on)
  dispatch.py              main-thread dispatch + per-op undo
  bridge_server.py         socket server + drain (GUI timer / headless loop)
  domains/                 scene, system, introspection, feedback handlers
  ui.py                    N-panel (Start/Stop)
scripts/blender_serve.py   headless launcher
tests/                     fake-bpy unit tests + a real-Blender smoke test
```

## Use it (visible GUI)

1. Install the server (editable): `python -m pip install -e .`
2. In Blender: Edit > Preferences > Add-ons > Install the `blender_addon/niua_mcp_bridge`
   folder, enable **Niua MCP Bridge**.
3. 3D Viewport sidebar (N) > **Niua** tab > **Start**. The bridge listens on
   `127.0.0.1:8765`.
4. Point your MCP client at the server:

```json
{
  "mcpServers": {
    "niua-blender": { "command": "python", "args": ["-m", "niua_blender_mcp"] }
  }
}
```

## Use it (headless)

```bash
blender --background --factory-startup --python scripts/blender_serve.py -- \
    "$PWD/blender_addon" 8765 0 600
```

## Security

`system.execute_python` is disabled by default on both sides. Enable for a trusted
local session with `NIUA_BLENDER_MCP_ALLOW_PYTHON=1` (server) and the N-panel toggle
(add-on). Bind the bridge to localhost only.

## Develop

```bash
python -m pytest            # unit + smoke (smoke auto-skips without a blender binary)
NIUA_SKIP_BLENDER=1 python -m pytest   # unit only
```
