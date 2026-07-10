# Architecture

*One page for a founder who got lost in the repo.*

## Why this exists

The niua pipeline is: a generator produces a rough 3D mesh -> this tool turns it into
a game-ready asset -> Godot imports it and plays it. The gap this repo closes is the
middle step. Generators are good at *shape*; they are bad at the boring, load-bearing
stuff a game engine actually needs: sane topology, unwrapped UVs, a material budget,
collision proxies, an export that survives a round-trip into Godot without warnings.
Someone has to be the technical artist who cleans that up. Here, an AI agent is that
technical artist, working inside a **visible, live Blender** it drives one verb at a
time — so a human can watch it work, and so every move is a real Blender operator, not
a guess.

The repo is two layers wearing one skin. They ship in the same processes today, but
they answer different questions, and only one of them knows what a "game asset" is.

## Part 1 — the interface (generic Blender remote control)

**Lives in:** `src/niua_blender_mcp/` (the MCP server, minus `finishing/` and
`evals/`) and `blender_addon/niua_mcp_bridge/` (the in-Blender add-on, minus
`finishing/` and the two policy domain files).

This half has zero opinions about games. It is a translation layer: MCP tool calls in,
Blender operators out.

- **kernel / bridge / dispatch / parity** — the server (`kernel/`, `bridge.py`) turns a
  typed tool call into a socket message; the add-on (`dispatch.py`,
  `bridge_server.py`) runs it on Blender's main thread and wraps it in per-op undo.
  `tests/test_parity.py` guarantees every server tool has a matching add-on handler
  and vice versa — the two halves can never drift apart silently.
- **~300 "hands" verbs** — `domains/*.py` on both sides: create/edit/transform
  objects, modifiers, materials, UVs, rigging, particles, physics, and a generated
  tier covering the rest of Blender's own operators via RNA introspection.
- **raw eyes** — `core/capture.py`, `core/silhouette.py` (turntable/ortho renders,
  silhouette masks). They measure and render; they don't judge.
- **session checkpoint/revert** — `core/session.py`. A generic undo-to-a-named-point
  primitive with no idea what it's protecting.

Nothing here knows what "game-ready" means. Delete `finishing/` and this half could
drive *any* Blender automation task — architecture visualization, VFX, whatever.

## Part 2 — the finishing tool (our methods)

**Lives in:** `src/niua_blender_mcp/finishing/` + `evals/`, and
`blender_addon/niua_mcp_bridge/finishing/` + the two policy domain files
(`domains/finishing_feedback.py`, `domains/asset_class.py`).

This half is where NIUA's opinion about "game-ready" is actually written down as
numbers.

- **Gates + asset-class budgets** (`finishing/gates.py`, `finishing/asset_classes.py`)
  — the numeric definition of game-ready: triangle/material/texture budgets, LOD and
  collision requirements, per asset-class (hard-surface prop, organic prop, etc).
- **`feedback.quality` / `feedback.readiness` / `feedback.capture_intake` /
  `feedback.preservation`** (`domains/finishing_feedback.py`) — the tools an agent
  calls to check its own work: `quality` measures the mesh against those budgets,
  `readiness` turns that into one order-free pass-fraction (the definition-of-done),
  and `capture_intake`/`preservation` are the do-no-harm pair — baseline a silhouette
  before editing, and prove afterward that the silhouette wasn't wrecked.
- **`evals/finisher.py`** — the reference finishing agent: no LLM, just a deterministic
  loop (checkpoint -> apply the smallest fix for a failing gate group -> re-measure ->
  keep if readiness didn't drop and preservation held, else revert). It exists so the
  benchmark measures the *tool surface*, not a model's taste.
- **`evals/godot_roundtrip.py` + `scripts/run_objective_benchmark.py`** — the proof
  system: does the finished asset actually import clean into a real headless Godot,
  and does readiness/preservation move in the right direction on real generator
  meshes? This is the thing that keeps the rest of this file honest.

## The rule

**Finishing may import interface. Interface must never import finishing (or evals).**
A verb doesn't need to know why it's being called; a policy doesn't work without the
verbs underneath it. This is enforced mechanically by `tests/test_layer_boundary.py`
(AST-based, no Blender required): every file outside the two `finishing/` packages and
the two named policy domain files is scanned for any import mentioning `finishing` or
`evals`, at any nesting depth, and fails the build if one is found.

**Known exceptions** (both intentional, both documented in code):

- `src/niua_blender_mcp/prompts.py` hosts `refine_mesh`, Part-2 finishing *doctrine*
  written as prose for the agent — policy content, sitting in a Part-1 file, because
  it's a prompt string rather than an import. Not caught by the AST test because it
  imports nothing from `finishing/`.
- `blender_addon/niua_mcp_bridge/domains/eyes.py` (`feedback.wire_shaded`,
  `feedback.lookdev`) folds `feedback.quality` analytics into its capture bundle, the
  same "render + policy snapshot" shape as `feedback.critique`. This surfaced while
  writing the boundary test and wasn't on the plan's original move list; rather than
  strip the `quality` field (which would change tool output — the surface is frozen)
  it's declared a third policy domain, alongside `finishing_feedback.py` and
  `asset_class.py`.

## Splitting it physically, later

Both sides already discover domains by directory scan — any module in `domains/` that
exposes `COMMANDS` (add-on) or `SPECS` (server) is picked up automatically, no
registration edit required (see `blender_addon/niua_mcp_bridge/domains/__init__.py`).
That means the finishing layer is already shaped like a plug-in: a physical split
later is "move the `finishing/` packages and the two-plus-one policy domain files into
a separate installable package that the interface half imports at runtime," not a
rewrite. The boundary test is what makes that move safe to attempt: if it's green
before the move, the import graph already has the right shape.
