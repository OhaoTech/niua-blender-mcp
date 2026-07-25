# Licensing

This repository ships **two programs under two licenses**. The split follows a real
process boundary, not a preference.

| Component | Path | License | Why |
|-----------|------|---------|-----|
| **MCP server** | `src/niua_blender_mcp/` | **Apache-2.0** (root `LICENSE`) | Standalone process. Never imports `bpy`. |
| **Blender add-on** | `blender_addon/niua_mcp_bridge/` | **GPL-3.0-or-later** (`blender_addon/LICENSE`) | Runs inside Blender and calls `bpy`. |

Everything else in the repo (`tests/`, `scripts/`, `docs/`) is Apache-2.0, except
material that imports the add-on package, which follows the add-on.

## Why the add-on must be GPL

Blender is licensed **GPL-2.0-or-later**. The Blender Foundation's position is that a
Python add-on using the `bpy` API is a derivative work of Blender, so any add-on that is
*distributed* must be under a GPL-compatible license. `blender_addon/` imports `bpy`
throughout and executes in Blender's own process, so GPL is not a choice we made — it is
a condition of the platform. (Blender's "or later" clause is what permits GPL-3.0 here.)

## Why the server is not GPL

The server is a separate program:

- it **never imports `bpy`** — there is no Blender code in its process;
- it declares **no dependencies** at all (`pyproject.toml`);
- it communicates with the add-on **only over a localhost TCP socket**, exchanging
  newline-delimited JSON (`src/niua_blender_mcp/bridge.py`);
- it runs and is tested **without Blender installed** — the offline test suite exercises
  the router, contracts, skills, and evaluation layer with no `bpy` present.

Two programs that talk at arm's length over a socket, with no shared address space and a
generic wire protocol, are separate works — the classic distinction between *linking* and
*inter-process communication*. Apache-2.0 therefore applies to the server, and its
permissive terms are compatible with GPL-3.0 for anyone redistributing the pair.

The architectural rule that keeps this true is enforced by the test suite in
`tests/test_layer_boundary.py` (import-direction guard) and `tests/test_parity.py`
(server/add-on command parity). **Keeping `bpy` out of `src/` is a licensing invariant,
not only a design one.**

## Practical consequences

- **Using the server** (embedding, building products on it, MCP clients): Apache-2.0 —
  permissive, patent grant included, no copyleft.
- **Distributing the add-on** (or a modified version): GPL-3.0-or-later — ship the source
  of your changes.
- **Publishing to Blender's extensions platform**: the add-on is already GPL-compatible.

## Contributing

Contributions are accepted under the license of the directory they touch. A change to
`blender_addon/` is contributed under GPL-3.0-or-later; a change anywhere else is
contributed under Apache-2.0.

---

*This file explains the project's licensing intent. It is not legal advice; if you are
redistributing this software commercially, review it with your own counsel.*
