# niua Blender MCP — asset polish for NIUA → Godot

**Start here:** [`START_HERE.md`](START_HERE.md) (one page). Everything else is optional.

## Product (not “all of Blender”)

```
generator mesh  →  polish in live Blender  →  Godot
```

Default finisher: **`bake_and_finish`**
(reduce to budget → shrinkwrap → bake → LOD/collision; keep only if form is measured and preserved).

Legacy **`make_game_ready`** (raw decimate, no bake) is **not** for dense AI meshes.

This repo also contains a generic Blender remote-control layer (~300 tools). That layer is a
**frozen library**. Day-to-day work is the finishing loop, not new domains.

## Quick start (GUI required for quality)

1. `python -m pip install -e .`
2. Blender → install/enable `blender_addon/niua_mcp_bridge` → **Niua** panel → **Start** (`127.0.0.1:8765`)
3. Finish fixtures:

```bash
python scripts/run_skill.py --skill bake_and_finish --port 8765 --outdir /tmp/niua_finish
```

Headless bridge works for plumbing tests, but **cannot measure** silhouette/fidelity
(no OpenGL) — fail-closed mode will **revert** finish moves. Use a visible Blender for real polish.

MCP client (agent drives the same bridge):

```json
{
  "mcpServers": {
    "niua-blender": { "command": "python", "args": ["-m", "niua_blender_mcp"] }
  }
}
```

## Layout (what matters)

```
START_HERE.md                 ← read this first
src/niua_blender_mcp/
  finishing/skills/           ← PRODUCT: bake_and_finish (default)
  evals/finisher.py           ← benchmark calls the default skill
  evals/benchmark/            ← real generator fixtures
  bridge.py / server.py       ← MCP ↔ Blender TCP
blender_addon/niua_mcp_bridge/
  finishing/                  ← gates, budgets, fidelity floors
  domains/objects.py          ← retopo, bake, shrinkwrap
  domains/finishing_feedback.py
scripts/run_skill.py          ← run the finisher on fixtures
docs/superpowers/             ← ARCHIVE (old plans/specs) — do not start here
```

## Develop

```bash
NIUA_SKIP_BLENDER=1 python -m pytest -q   # unit only
python -m pytest -q                      # + smoke if blender is installed
```

## Security

`system.execute_python` is off by default. Localhost-only bridge. Enable Python only for trusted sessions (`NIUA_BLENDER_MCP_ALLOW_PYTHON=1` + N-panel).

## Deeper docs (optional)

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — interface vs finishing split (short)
- [`docs/DESIGN.md`](docs/DESIGN.md) — original full design (historical)
- [`docs/reports/`](docs/reports/) — live run evidence
