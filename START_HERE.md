# START HERE — NIUA Blender polish

**Read this page. Ignore the rest of the repo until something on this page points you there.**

## What this product is (one sentence)

```
a generator makes a rough mesh  →  THIS TOOL polishes it  →  an engine ships it
```

You are not building “all of Blender for agents.” You are building the **middle step**:
turn a dense generator mesh into a **budgeted, bake-friendly, importable** game asset
without turning it into a faceted blob.

## The only loop that matters

```
1. import mesh
2. capture intake (baseline for “do no harm”)
3. reduce to triangle budget (retopo, or decimate fallback)
4. shrinkwrap onto high-poly → UV → bake normal/AO
5. PBR / LOD / collision / apply transforms
6. keep a step only if readiness held AND silhouette + fidelity are measured and pass
7. export GLB → verify it imports clean in a real engine
```

**Default skill:** `bake_and_finish`  
**Default entry:** `evals/finisher.py` → that skill  
**Hard rule:** unmeasured quality = **revert** (never silent pass)

Legacy skill `make_game_ready` = raw decimate, **no bake**. Do not use for dense AI meshes.

## Files you may touch (the island)

| Role | Path |
|------|------|
| **The product loop** | `src/niua_blender_mcp/finishing/skills/bake_and_finish.py` |
| Budgets / classes | `src/niua_blender_mcp/finishing/asset_classes.py` |
| Gate definitions (addon) | `blender_addon/niua_mcp_bridge/finishing/gates.py` |
| Fidelity / silhouette floors | `blender_addon/niua_mcp_bridge/finishing/preservation_ledger.py` |
| Quality / readiness tools | `blender_addon/niua_mcp_bridge/domains/finishing_feedback.py` |
| Retopo / bake / shrinkwrap | `blender_addon/niua_mcp_bridge/domains/objects.py` |
| Benchmark entry | `src/niua_blender_mcp/evals/finisher.py` |
| Run one skill | `scripts/run_skill.py` |
| Real fixtures | `src/niua_blender_mcp/evals/benchmark/` |

## Files you should ignore (until the island is boring)

| Area | Why ignore |
|------|------------|
| `docs/superpowers/plans` + `specs` | Build archaeology (~80 md files). Archive. |
| Most of `domains/*` (sequencer, spreadsheet, topbar, …) | Frozen library — remote Blender verbs, not the product |
| RNA / manifest generation | Platform plumbing; only after Blender upgrade |
| `make_game_ready.py` | Legacy blob path |
| `workflows/`, old altimeter / layer2 HTML | Historical |
| `docs/PLAN.md`, long DESIGN details | Background; not day-to-day |

**Freeze rule:** do **not** add new Blender domain tools unless `bake_and_finish` cannot complete a step without them.

## How to run (GUI — required for quality gates)

Headless has no OpenGL → preservation/fidelity unavailable → **every move reverts**.  
Polish that can *keep* changes needs a **visible Blender** with the bridge started.

```bash
# terminal 1 — install once
python -m pip install -e .

# In Blender GUI: enable add-on blender_addon/niua_mcp_bridge → Niua panel → Start (port 8765)

# terminal 2 — finish the 5 real fixtures with the default skill
python scripts/run_skill.py --skill bake_and_finish --port 8765 --outdir /tmp/niua_finish
```

Offline tests only (no quality proof):

```bash
NIUA_SKIP_BLENDER=1 python -m pytest -q
```

## Definition of done (v1)

An asset is shippable only if:

1. Triangle budget for its asset class  
2. Silhouette + surface fidelity **measured** and pass  
3. Export imports clean in a headless engine  
4. No Blender crash  

Not done yet on all fixtures (UV, multipart crash, some organics). That is the work —
not more architecture.

## Proofs (evidence, not vibes)

Latest layer proofs: [`docs/reports/layer-proofs-2026-07-14.md`](docs/reports/layer-proofs-2026-07-14.md)

| Layer | Status (that report + 2026-07-15 re-proof) |
|-------|----------------------|
| Loyal Blender interface | **Working** (live 5/5) |
| Our craft verbs + export check | **Working** (retopo budget, bake maps, LOD, import check) |
| Fail-closed + multipart retopo | **Fixed & re-proven** (no score drift; multi-island uses decimate-only) |
| Top-tier visual quality (fidelity/UV) | **Not cleared** — needs GUI fidelity run |

## If you get lost again

1. Open this file.  
2. Open `bake_and_finish.py`.  
3. Ask: does my change improve steps 3–7 above? If no, stop.
