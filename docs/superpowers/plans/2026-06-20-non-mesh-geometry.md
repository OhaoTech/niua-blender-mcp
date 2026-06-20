# Non-Mesh Geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build subsystem 6: a curated `geometry.*` surface for creating, inspecting, adjusting, and converting curves, text, NURBS surfaces, metaballs, and grease pencil objects.

**Architecture:** Add a new domain pack. Server specs live in `src/niua_blender_mcp/domains/geometry.py`; add-on handlers live in `blender_addon/niua_mcp_bridge/domains/geometry.py`; fake-bpy tests live in `tests/domains/test_geometry.py`; live Blender smoke extends `tests/test_smoke_headless.py`. Creation handlers dispatch Blender primitive operators and normalize created-object reporting; setters write data-block properties directly; conversion uses `ctx.ensure(active=obj, mode="OBJECT", select=[obj])` and `bpy.ops.object.convert`.

**Tech Stack:** Python 3.11+, stdlib only, pytest, fake-bpy tests, real Blender 5.1.1 headless smoke.

## Global Constraints

- No runtime dependencies.
- Use `geometry.*` for subsystem-6 curated tools.
- Do not implement curve point dragging, grease-pencil stroke authoring, keyboard text editing, modal handles, or viewport mouse workflows here; subsystem 12 owns GUI/event parity.
- Keep object lifecycle/transforms in `object.*`; geometry tools may set transform kwargs only during primitive creation.
- Every curated tool must have a server `ToolSpec` and matching add-on `Command`.
- Mutating tools must be marked `mutates=True` and `feedback="viewport"`.
- Run tests from repo root with `pytest`.

---

## Tool Interfaces

- `geometry.create_curve(type, name="", radius=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`
- `geometry.create_text(name="", body="Text", align_x="LEFT", align_y="TOP_BASELINE", size=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`
- `geometry.create_surface(type, name="", radius=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`
- `geometry.create_metaball(type="BALL", name="", radius=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`
- `geometry.create_grease_pencil(type="EMPTY", name="", radius=1.0, use_in_front=False, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`
- `geometry.report(object)`
- `geometry.set_curve(object, bevel_depth?, bevel_resolution?, extrude?, resolution_u?, render_resolution_u?, dimensions?, fill_mode?, use_fill_caps?)`
- `geometry.set_text(object, body?, align_x?, align_y?, size?, space_line?, offset_x?, offset_y?)`
- `geometry.convert_to_mesh(object, name="", keep_original=False)`

## Task 1: Geometry Specs, Report, Curve Creation

**Files:**
- Create: `tests/domains/test_geometry.py`
- Create: `src/niua_blender_mcp/domains/geometry.py`
- Create: `blender_addon/niua_mcp_bridge/domains/geometry.py`

**Interfaces:**
- Adds server specs for `geometry.report` and `geometry.create_curve`.
- Adds add-on helpers `_vec`, `_created`, `_object_report`, `_curve_data_report`, and `_primitive_kwargs`.
- Implements `geometry.report`.
- Implements `geometry.create_curve`.

- [ ] Write fake-bpy tests that assert router contains `geometry.report` and `geometry.create_curve`.
- [ ] Write fake-bpy tests for reporting a curve object's splines and curve settings.
- [ ] Write fake-bpy tests for creating a `BEZIER_CIRCLE` curve with name, radius, location, rotation, and scale.
- [ ] Run `pytest tests/domains/test_geometry.py -v` and verify failures are missing module/spec/unknown command failures.
- [ ] Add server specs for `geometry.report` and `geometry.create_curve`.
- [ ] Add add-on handlers and helpers.
- [ ] Run `pytest tests/domains/test_geometry.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add geometry curve tools"`.

## Task 2: Text, Surface, Metaball, and Grease Pencil Creation

**Files:**
- Modify: `tests/domains/test_geometry.py`
- Modify: `src/niua_blender_mcp/domains/geometry.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/geometry.py`

**Interfaces:**
- Adds `geometry.create_text`.
- Adds `geometry.create_surface`.
- Adds `geometry.create_metaball`.
- Adds `geometry.create_grease_pencil`.

- [ ] Write fake-bpy tests for text creation setting body, align, and size.
- [ ] Write fake-bpy tests for surface, metaball, and grease pencil creation operator dispatch and report shape.
- [ ] Write router-surface tests for all four new commands.
- [ ] Run targeted tests and verify failures.
- [ ] Add server specs.
- [ ] Add add-on handlers.
- [ ] Run `pytest tests/domains/test_geometry.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add non-mesh creation tools"`.

## Task 3: Curve and Text Setters

**Files:**
- Modify: `tests/domains/test_geometry.py`
- Modify: `src/niua_blender_mcp/domains/geometry.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/geometry.py`

**Interfaces:**
- Adds `geometry.set_curve`.
- Adds `geometry.set_text`.
- `geometry.set_curve` supports `CURVE`, `FONT`, and `SURFACE`; rejects other object types with `precondition_failed`.
- `geometry.set_text` supports only `FONT`; rejects other object types with `precondition_failed`.

- [ ] Write fake-bpy tests for `geometry.set_curve` updating only provided fields.
- [ ] Write fake-bpy tests for `geometry.set_curve` rejecting a metaball.
- [ ] Write fake-bpy tests for `geometry.set_text` updating only provided text fields.
- [ ] Write fake-bpy tests for `geometry.set_text` rejecting a curve.
- [ ] Write router-surface tests for both new commands.
- [ ] Run targeted tests and verify failures.
- [ ] Add server specs.
- [ ] Add add-on handlers.
- [ ] Run `pytest tests/domains/test_geometry.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add geometry data setters"`.

## Task 4: Convert To Mesh

**Files:**
- Modify: `tests/domains/test_geometry.py`
- Modify: `src/niua_blender_mcp/domains/geometry.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/geometry.py`

**Interfaces:**
- Adds `geometry.convert_to_mesh`.
- Uses `ctx.ensure(active=obj, mode="OBJECT", select=[obj])`.
- Calls `bpy.ops.object.convert(target="MESH", keep_original=<bool>)`.
- Returns the report for the active converted object and renames it when `name` is provided.

- [ ] Write fake-bpy tests that assert object conversion uses object context and passes target/keep_original.
- [ ] Write fake-bpy tests that conversion renames the active converted mesh when `name` is provided.
- [ ] Write router-surface test for `geometry.convert_to_mesh`.
- [ ] Run targeted tests and verify failures.
- [ ] Add server spec.
- [ ] Add add-on handler.
- [ ] Run `pytest tests/domains/test_geometry.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add geometry mesh conversion"`.

## Task 5: Live Smoke, Roadmap, Final Verification

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

**Interfaces:**
- Adds `test_non_mesh_geometry_workflow`.
- Updates roadmap current focus to subsystem 6 complete and subsystem 7 next.

- [ ] Add a live smoke test that creates a Bezier circle curve, reports it, sets bevel/extrude/resolution, creates and updates text, creates and reports a surface/metaball/grease pencil, converts the curve to mesh, and verifies the converted type is `MESH`.
- [ ] Run `pytest tests/test_smoke_headless.py -v`.
- [ ] Update the roadmap with subsystem 6 completion notes.
- [ ] Run `pytest`.
- [ ] Run `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'geometry.create_curve','geometry.create_text','geometry.create_surface','geometry.create_metaball','geometry.create_grease_pencil','geometry.report','geometry.set_curve','geometry.set_text','geometry.convert_to_mesh'}; print(required <= names)"` and verify it prints `True`.
- [ ] Run `git status --short --branch`.
- [ ] Commit with `git commit -m "test: cover non-mesh geometry workflow"`.

## Final Verification

- [ ] `pytest`
- [ ] `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'geometry.create_curve','geometry.create_text','geometry.create_surface','geometry.create_metaball','geometry.create_grease_pencil','geometry.report','geometry.set_curve','geometry.set_text','geometry.convert_to_mesh'}; print(required <= names)"`
- [ ] `git status --short --branch`
