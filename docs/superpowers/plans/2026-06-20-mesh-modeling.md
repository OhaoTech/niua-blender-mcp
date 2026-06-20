# Mesh Modeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build subsystem 5: a deterministic curated `mesh.*` surface for mesh element selection and stable topology edit operations.

**Architecture:** Extend the existing mesh domain instead of adding a new pack. Server specs stay in `src/niua_blender_mcp/domains/mesh.py`; add-on handlers stay in `blender_addon/niua_mcp_bridge/domains/mesh.py`; fake-bpy coverage extends `tests/domains/test_mesh.py`; live Blender smoke extends `tests/test_smoke_headless.py`. Selection-by-index writes mesh data selection flags in object mode, then topology operators run through the existing `ctx.ensure(..., mode="EDIT")` and `ctx.check_poll(...)` path.

**Tech Stack:** Python 3.11+, stdlib only, pytest, fake-bpy tests, real Blender 5.1.1 headless smoke.

## Global Constraints

- No runtime dependencies.
- Use `mesh.*` for subsystem-5 curated tools.
- Keep existing `mesh.extrude`, `mesh.bevel`, `mesh.inset`, `mesh.subdivide`, `mesh.recalc_normals`, `mesh.shade_smooth`, and `mesh.report` behavior compatible.
- Do not implement viewport mouse picking, knife drawing, box/lasso selection, gizmos, or UI event shortcuts here; subsystem 12 owns GUI/event parity.
- Every curated tool must have a server `ToolSpec` and matching add-on `Command`.
- Mutating tools must be marked `mutates=True` and `feedback="viewport"`.
- Run tests from repo root with `pytest`.

---

## Tool Interfaces

- `mesh.selection_report(object="")`
- `mesh.select_all(object="", action="SELECT")`
- `mesh.select_by_index(object, mode, indices, action="REPLACE")`
- `mesh.delete(object="", type="VERT")`
- `mesh.dissolve(object="", type="EDGES", use_verts=False, angle_limit=0.0872665, use_dissolve_boundaries=False)`
- `mesh.merge(object="", type="CENTER", uvs=True)`
- `mesh.remove_doubles(object="", threshold=0.0001)`
- `mesh.tris_to_quads(object="", face_threshold=40.0, shape_threshold=40.0)`
- `mesh.quads_to_tris(object="", quad_method="BEAUTY", ngon_method="BEAUTY")`
- `mesh.fill(object="", beauty=True)`
- `mesh.edge_face_add(object="")`

## Task 1: Selection Report and Select-All

**Files:**
- Modify: `tests/domains/test_mesh.py`
- Modify: `src/niua_blender_mcp/domains/mesh.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/mesh.py`

**Interfaces:**
- Adds `mesh.selection_report`.
- Adds `mesh.select_all`.
- Helper `_selection_report(obj) -> dict` returns object name, selected indices, and counts.
- Helper `_mesh_items(mesh, mode) -> list[Any]` maps `VERT`, `EDGE`, `FACE` to mesh vertices/edges/polygons.

- [ ] Write failing fake-bpy tests for `mesh.selection_report` reading selected vertex/edge/face indices.
- [ ] Write failing fake-bpy tests for `mesh.select_all(action="DESELECT")` calling `mesh.select_all` in edit mode and pushing one undo step.
- [ ] Write failing router-surface test for `mesh.selection_report` and `mesh.select_all`.
- [ ] Run `pytest tests/domains/test_mesh.py -v` and verify the new tests fail on missing commands/specs.
- [ ] Add server specs for `mesh.selection_report` and `mesh.select_all`.
- [ ] Add add-on handlers and helpers.
- [ ] Run `pytest tests/domains/test_mesh.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add mesh selection read tools"`.

## Task 2: Select By Index

**Files:**
- Modify: `tests/domains/test_mesh.py`
- Modify: `src/niua_blender_mcp/domains/mesh.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/mesh.py`

**Interfaces:**
- Adds `mesh.select_by_index`.
- `mode` enum: `VERT`, `EDGE`, `FACE`.
- `action` enum: `REPLACE`, `ADD`, `REMOVE`, `TOGGLE`.
- `indices` is a comma-separated string of zero-based integers.
- Handler sets `context.tool_settings.mesh_select_mode` to match the requested mode.

- [ ] Write failing fake-bpy tests for replace/add/remove/toggle behavior.
- [ ] Write failing fake-bpy test for invalid empty/non-integer/out-of-range indices returning `invalid_params`.
- [ ] Write failing router-surface test for `mesh.select_by_index`.
- [ ] Run targeted tests and verify failures.
- [ ] Add server spec.
- [ ] Add parsing and selection mutation helpers.
- [ ] Run `pytest tests/domains/test_mesh.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add mesh index selection"`.

## Task 3: Delete and Dissolve

**Files:**
- Modify: `tests/domains/test_mesh.py`
- Modify: `src/niua_blender_mcp/domains/mesh.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/mesh.py`

**Interfaces:**
- Adds `mesh.delete`.
- Adds `mesh.dissolve`.
- Delete type enum: `VERT`, `EDGE`, `FACE`, `EDGE_FACE`, `ONLY_FACE`.
- Dissolve type enum: `VERTS`, `EDGES`, `FACES`, `LIMITED`.

- [ ] Write failing fake-bpy tests for `mesh.delete(type="FACE")` operator call and return shape.
- [ ] Write failing fake-bpy tests for each `mesh.dissolve` type dispatching to the correct Blender op.
- [ ] Write failing router-surface tests for `mesh.delete` and `mesh.dissolve`.
- [ ] Run targeted tests and verify failures.
- [ ] Add server specs.
- [ ] Add add-on handlers using `_edit(...)`.
- [ ] Run `pytest tests/domains/test_mesh.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add mesh delete dissolve tools"`.

## Task 4: Merge, Cleanup, Convert, and Fill

**Files:**
- Modify: `tests/domains/test_mesh.py`
- Modify: `src/niua_blender_mcp/domains/mesh.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/mesh.py`

**Interfaces:**
- Adds `mesh.merge`.
- Adds `mesh.remove_doubles`.
- Adds `mesh.tris_to_quads`.
- Adds `mesh.quads_to_tris`.
- Adds `mesh.fill`.
- Adds `mesh.edge_face_add`.

- [ ] Write failing fake-bpy tests for every new operator call and returned `applied` value.
- [ ] Write failing router-surface tests for all six tools.
- [ ] Run targeted tests and verify failures.
- [ ] Add server specs.
- [ ] Add add-on handlers.
- [ ] Run `pytest tests/domains/test_mesh.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add mesh topology edit tools"`.

## Task 5: Live Smoke, Roadmap, Final Verification

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

**Interfaces:**
- Adds `test_mesh_selection_topology_workflow`.
- Updates roadmap current focus to subsystem 5 complete and subsystem 6 next.

- [ ] Add a live smoke test that creates a cube, reports 6 faces, selects one face by index, verifies selection report, deletes the selected face, and verifies face count is 5.
- [ ] Add live checks for conversion/cleanup operators on a separate cube: `mesh.select_all`, `mesh.quads_to_tris`, `mesh.tris_to_quads`, and `mesh.remove_doubles`.
- [ ] Run `pytest tests/test_smoke_headless.py -v`.
- [ ] Update the roadmap with subsystem 5 completion notes.
- [ ] Run `pytest`.
- [ ] Run `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'mesh.selection_report','mesh.select_all','mesh.select_by_index','mesh.delete','mesh.dissolve','mesh.merge','mesh.remove_doubles','mesh.tris_to_quads','mesh.quads_to_tris','mesh.fill','mesh.edge_face_add'}; print(required <= names)"` and verify it prints `True`.
- [ ] Run `git status --short --branch`.
- [ ] Commit with `git commit -m "test: cover mesh selection topology workflow"`.

## Final Verification

- [ ] `pytest`
- [ ] `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'mesh.selection_report','mesh.select_all','mesh.select_by_index','mesh.delete','mesh.dissolve','mesh.merge','mesh.remove_doubles','mesh.tris_to_quads','mesh.quads_to_tris','mesh.fill','mesh.edge_face_add'}; print(required <= names)"`
- [ ] `git status --short --branch`
