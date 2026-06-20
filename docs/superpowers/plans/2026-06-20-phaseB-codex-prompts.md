# Phase-B follow-up — Codex prompts

Context for all prompts: this repo is a standalone Blender MCP. Layer-2 Phase A is
built (topology eye `feedback.topology`, eval stack in `src/niua_blender_mcp/evals/`,
playbooks in `src/niua_blender_mcp/playbooks/`, seed craft verb `model.retopo_quads`).
A live convergence loop (`workflows/converge_modeling.mjs`) drives a visible Blender;
its agents model toward the `modeling_prop` battery task and a 3-lens judge scores the
renders. **Finding from two live runs:** with the topology eye fixed, the judge rose
from ~3.5 to a peak of 6 but plateaued below the 7.0 bar — the bottleneck is now
*craft depth* (the agent can only clean topology + basic bevels) and *judge variance*.
These prompts raise the ceiling and make the bar fair. Standalone repo: no "niua"/
Godot references in code. Conventions: `from __future__ import annotations`; server
`SPECS` ↔ addon `COMMANDS` parity (a test enforces it); `bpy` only via `ctx.bpy`;
mutating tools push undo AFTER success (see `dispatch.py`); run tests with `pytest`.

---

## Prompt 1 — Senior modeling craft verbs (the ceiling lever)

> Add two tier-1 composite "craft verbs" that encode senior hard-surface moves, so the
> convergence agent can build real prop detail instead of only cleaning topology. Mirror
> the existing `model.retopo_quads` verb exactly (server spec in
> `src/niua_blender_mcp/domains/modeling_verbs.py`, addon handler in
> `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`, both auto-discovered;
> `mutates=True`, `feedback="viewport"`, `tier="curated"`; run inside
> `ctx.ensure(active=obj, mode="EDIT", select=[obj])`).
>
> 1. `model.bevel_edges` — params `object: Str(required)`, `angle: Float(default=30, 0..180)`
>    (bevel only edges sharper than this angle), `width: Float(default=0.02, min=0)`,
>    `segments: Int(default=2, min=1, max=12)`. Handler: in edit mode, deselect all, select
>    edges by sharpness (`mesh.edges_select_sharp` with `sharpness=radians(angle)`), then
>    `mesh.bevel(offset=width, segments=segments, affect='EDGES')`. Return
>    `{"object", "applied": ["edges_select_sharp","bevel"], "segments": segments}`.
> 2. `model.recess_panels` — params `object: Str(required)`, `inset: Float(default=0.08, min=0)`,
>    `depth: Float(default=0.04, min=0)` (the recessed-panel "crate" look). Handler: edit mode,
>    select all faces, `mesh.inset_faces(thickness=inset, use_individual=True)`, then push the
>    new inner faces inward by `depth` (e.g. `mesh.inset_faces(thickness=0, depth=-depth)` or an
>    extrude+move along normals). Return `{"object","applied":[...],"inset":inset,"depth":depth}`.
>
> Tests in `tests/domains/test_modeling_verbs.py` using the existing fake-bpy that records
> `bpy.ops.*` calls (mirror the `model.retopo_quads` test): assert each verb runs its operator
> sequence in order and returns the documented dict. Then: `pytest` green; verify both names
> appear via `python -c "from niua_blender_mcp.domains import build_router as b; print({s.name for s in b().specs()} >= {'model.bevel_edges','model.recess_panels'})"` → `True`. Commit each verb separately.

## Prompt 2 — Deepen the modeling playbook

> Extend `src/niua_blender_mcp/playbooks/modeling.md` with a concrete, senior-level recipe the
> convergence agent can follow to build a clean game-ready crate (the current `modeling_prop`
> task brief). Add a section "Recipe — hard-surface crate" giving the EXACT ordered tool calls
> a senior would use, e.g.: 1) start from a clean cube, apply scale; 2) `model.recess_panels`
> for the side panels (give sensible inset/depth); 3) `model.bevel_edges` (angle ~30, segments 2)
> for chamfered edges; 4) `model.retopo_quads` to keep all-quad; 5) shade smooth with auto-smooth
> angle; 6) verify with `feedback.quality` (quad_ratio ≥ 0.95, ngons 0, non-manifold 0) and
> `feedback.topology`. Also add a "What pushes a prop from 5 to 8" heuristics block (purposeful
> edge loops, supporting loops near bevels, even quad density, believable proportions, no poles on
> silhouette). Keep it concise (~30-50 lines). The loader `load_playbook("modeling")` already
> reads this file; ensure `pytest tests/test_playbooks.py` stays green. Commit.

## Prompt 3 — Calibrate the judge (reduce variance, make the bar fair)

> The taste judge swings (6→5 on similar output) and never crosses 7.0 even on a clean crate,
> so add explicit score anchors to the rubric and make the threshold intentional. Edit
> `src/niua_blender_mcp/evals/battery/modeling_prop/rubric.md`: add a "## Score anchors" section —
> `0-2: default primitive / blockout`; `3-4: primitive with minor edits, no design intent`;
> `5-6: clean, recognizable, simple prop (acceptable but unremarkable)`; `7-8: senior game-ready —
> purposeful edge flow, supporting loops, believable detail, clean shading`; `9-10: exceptional`.
> Add a line: "Judge ONLY what is visible in the supplied renders; if the topology overlay is
> readable, score topology on it rather than defaulting low." Keep `judge_threshold: 7.0` in
> `task.json` (7 = the senior bar by design). The rubric is loaded by `load_task('modeling_prop')`;
> ensure `pytest tests/evals/test_battery.py` stays green (it asserts a non-empty rubric). Commit.

---

### Not in these prompts (orchestration — handled by the runner, not Codex)
- `workflows/converge_modeling.mjs`: add keep-best (`session.checkpoint` the best round,
  `session.revert` when a round regresses) and honor the `maxRounds` arg. This is the loop
  script run by the Workflow tool, not pytest-testable code — the orchestrator owns it.
