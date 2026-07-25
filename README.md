# Blender Finisher

**Rough mesh → measured game-ready asset → Godot.** An MCP server with a ruler.

Point an LLM at a dense, generated mesh and get back a budgeted, baked, importable game
asset — where every step that cannot be *proven* to preserve the form is reverted.

> Package name is `niua-blender-mcp`; the product is the finisher.
> **New here?** Read [`START_HERE.md`](START_HERE.md) — one page, then come back.

![architecture](docs/images/architecture.svg)

## What makes it different

Most Blender integrations answer *“can an LLM drive Blender?”* — that is strata ①–② above,
and this repo has one of the larger ones (~305 curated, schema-validated tools).

The product is strata ③–④: **it measures the result and refuses what it cannot prove.**

| | Typical Blender MCP | Blender Finisher |
|---|---|---|
| Drive Blender from an LLM | ✅ | ✅ ~305 tools, 48 domains |
| Run arbitrary `bpy` | ✅ (usually ungated) | ✅ **off by default** |
| Measure the result | ✖ | ✅ silhouette IoU · surface-fidelity SSIM · topology |
| Asset budgets & gates | ✖ | ✅ per asset class (character / prop / hard-surface) |
| Revert unproven work | ✖ | ✅ **fail-closed** — unmeasured is not passed |
| Verify downstream | ✖ | ✅ Godot round-trip test |

## The loop

```
1. import mesh
2. capture intake            ← the "do no harm" baseline
3. reduce to triangle budget (retopo, or decimate fallback)
4. shrinkwrap → UV → bake normal/AO
5. PBR / LOD / collision / apply transforms
6. keep the step ONLY if readiness held and form is measured + preserved
7. export GLB → Godot imports clean
```

Default skill: **`bake_and_finish`**. (Legacy `make_game_ready` — raw decimate, no bake —
is *not* for dense AI meshes.)

## Quick start

A **visible** Blender is required for real quality: measurement needs OpenGL.

1. `python -m pip install -e .`
2. Blender → install/enable `blender_addon/niua_mcp_bridge` → **Niua** panel → **Start** (`127.0.0.1:8765`)
3. Finish the benchmark fixtures:

```bash
python scripts/run_skill.py --skill bake_and_finish --port 8765 --outdir /tmp/niua_finish
```

Headless works for plumbing tests but **cannot measure** silhouette/fidelity — fail-closed
mode will revert finishing moves rather than pass them blind.

Drive it from an MCP client:

```json
{
  "mcpServers": {
    "niua-blender": { "command": "python", "args": ["-m", "niua_blender_mcp"] }
  }
}
```

## Status — honest

Pre-1.0. On the objective benchmark of real generator meshes, **3 of 5 fixtures finish
game-ready**; `real_character` still shows surface noise and `real_multipart` has a
crash-guard that has not yet been re-validated end to end.

That number exists *because the ruler exists* — the interesting claim is not "3/5", it is
that the tool can tell you at all, and reverts the other two instead of shipping them.

## Layout

```
START_HERE.md                 ← read this first
src/niua_blender_mcp/         ← MCP server (Apache-2.0, never imports bpy)
  finishing/skills/             PRODUCT: bake_and_finish (default)
  evals/finisher.py             benchmark entry → the default skill
  evals/benchmark/              real generator fixtures
  bridge.py / server.py         MCP ↔ Blender socket
blender_addon/niua_mcp_bridge/ ← Blender add-on (GPL-3.0, imports bpy)
  finishing/                    gates, budgets, fidelity floors
  domains/objects.py            retopo, bake, shrinkwrap
scripts/run_skill.py          ← run the finisher on fixtures
docs/superpowers/             ← ARCHIVE (old plans) — do not start here
```

## Develop

```bash
NIUA_SKIP_BLENDER=1 python -m pytest -q   # unit only
python -m pytest -q                       # + smoke if blender is installed
```

Three invariants are enforced by the test suite: the interface never imports finishing, the server never
imports `bpy`, and every server tool has a matching add-on handler.

## Security

`system.execute_python` is **off by default**; the bridge is localhost-only. Enable Python
only for trusted local sessions (`NIUA_BLENDER_MCP_ALLOW_PYTHON=1`, or the N-panel toggle).

## License

Two programs, two licenses, split on a real process boundary:

| Component | License |
|---|---|
| MCP server (`src/`) — never imports `bpy` | **Apache-2.0** |
| Blender add-on (`blender_addon/`) — runs inside Blender | **GPL-3.0-or-later** |

The add-on calls `bpy`, so Blender's GPL applies to it; the server is a separate process
that talks over a socket and is permissively licensed. See [`LICENSING.md`](LICENSING.md).

## Deeper docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the four strata and the loop
- [`LICENSING.md`](LICENSING.md) — why the server is Apache-2.0 and the add-on is GPL
- [`docs/reports/`](docs/reports/) — live run evidence, including the honest failures
- [`docs/DESIGN.md`](docs/DESIGN.md) — original full design (historical)
