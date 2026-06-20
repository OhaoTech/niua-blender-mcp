# Context / Selection / Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build subsystem 3: a curated `context.*` MCP surface for active object, selection, interaction mode, mesh select mode, area discovery, and operator poll checks.

**Architecture:** Follow the existing domain-pack pattern. Server specs live in `src/niua_blender_mcp/domains/context.py`; add-on handlers live in `blender_addon/niua_mcp_bridge/domains/context.py`; fake-bpy tests live in `tests/domains/test_context_domain.py`; live smoke extends `tests/test_smoke_headless.py`. Permanent context mutations use Blender data/API state directly; temporary proposed context for poll checks uses the existing `ctx.ensure(...)` resolver.

**Tech Stack:** Python 3.11+, stdlib only, pytest, fake-bpy tests, real Blender 5.1 headless smoke.

## Global Constraints

- No runtime dependencies.
- Use `context.*` for subsystem-3 curated tools.
- Do not implement GUI keyboard/mouse events here; subsystem 12 owns GUI parity.
- Do not implement object creation/transforms here; subsystem 4 owns them.
- Every curated tool must have a server `ToolSpec` and matching add-on `Command`.
- Mutating tools must be marked `mutates=True` where they permanently change active object, selection, mode, or mesh select mode.
- `context.poll_operator` is read-only and must not invoke the operator or push undo.
- Run tests from repo root with `pytest`.

---

## Tool Interfaces

- `context.info()`
- `context.areas()`
- `context.set_active(object, select=True)`
- `context.select_objects(objects, action="REPLACE", active="")`
- `context.select_all(action="DESELECT")`
- `context.mode_set(mode, object="", select=True)`
- `context.mesh_select_mode(mode)`
- `context.poll_operator(idname, object="", mode="", select="")`

## Task 1: Context Info and Area Discovery

**Files:**
- Create: `tests/domains/test_context_domain.py`
- Create: `src/niua_blender_mcp/domains/context.py`
- Create: `blender_addon/niua_mcp_bridge/domains/context.py`

**Interfaces:**
- Produces `context.info` and `context.areas`.
- Add-on helper `_context_summary(ctx) -> dict` returns scene/view layer/workspace, context mode, object mode, active object, selected objects, mesh select mode, and area summary.

- [ ] Write fake-bpy tests for `context.info` and `context.areas`.
- [ ] Run `pytest tests/domains/test_context_domain.py -v` and verify failures are `unknown command`.
- [ ] Implement server specs for `context.info` and `context.areas`.
- [ ] Implement add-on read handlers and helpers.
- [ ] Run `pytest tests/domains/test_context_domain.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add context read tools"`.

## Task 2: Active Object and Selection Tools

**Files:**
- Modify: `tests/domains/test_context_domain.py`
- Modify: `src/niua_blender_mcp/domains/context.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/context.py`

**Interfaces:**
- Adds `context.set_active`, `context.select_objects`, and `context.select_all`.
- `objects` is a comma-separated object name string.
- Selection actions: `REPLACE`, `ADD`, `REMOVE`, `TOGGLE`.
- Select-all actions: `SELECT`, `DESELECT`, `INVERT`.
- Hidden or unselectable objects raise `precondition_failed`.

- [ ] Write fake-bpy tests for active set with selection side effect.
- [ ] Write fake-bpy tests for hidden/unselectable active guards.
- [ ] Write fake-bpy tests for selection actions and select-all actions.
- [ ] Run `pytest tests/domains/test_context_domain.py -v` and verify failures.
- [ ] Implement server specs.
- [ ] Implement add-on handlers using `view_layer.objects.active`, `select_set`, and `select_get`.
- [ ] Run `pytest tests/domains/test_context_domain.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add context selection tools"`.

## Task 3: Mode and Mesh Select Mode Tools

**Files:**
- Modify: `tests/domains/test_context_domain.py`
- Modify: `src/niua_blender_mcp/domains/context.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/context.py`

**Interfaces:**
- Adds `context.mode_set` and `context.mesh_select_mode`.
- Mode values: `OBJECT`, `EDIT`, `POSE`, `SCULPT`, `VERTEX_PAINT`, `WEIGHT_PAINT`, `TEXTURE_PAINT`, `PARTICLE_EDIT`, `EDIT_GPENCIL`, `SCULPT_GREASE_PENCIL`, `PAINT_GREASE_PENCIL`, `WEIGHT_GREASE_PENCIL`, `VERTEX_GREASE_PENCIL`, `SCULPT_CURVES`.
- Mesh select mode values: `VERT`, `EDGE`, `FACE`, `VERT_EDGE`, `VERT_FACE`, `EDGE_FACE`, `VERT_EDGE_FACE`.

- [ ] Write fake-bpy tests for mode setting with optional object activation.
- [ ] Write fake-bpy tests for mode-set poll/runtime failures becoming `precondition_failed`.
- [ ] Write fake-bpy tests for mesh select mode mapping.
- [ ] Run `pytest tests/domains/test_context_domain.py -v` and verify failures.
- [ ] Implement server specs.
- [ ] Implement add-on handlers using `bpy.ops.object.mode_set` and `context.tool_settings.mesh_select_mode`.
- [ ] Run `pytest tests/domains/test_context_domain.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add context mode tools"`.

## Task 4: Operator Poll, Live Smoke, Roadmap, Final Verification

**Files:**
- Modify: `tests/domains/test_context_domain.py`
- Modify: `src/niua_blender_mcp/domains/context.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/context.py`
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

**Interfaces:**
- Adds `context.poll_operator`.
- Live smoke verifies: create two objects, `context.set_active`, selection actions, `context.mode_set(EDIT)`, `context.mesh_select_mode(EDGE)`, `context.poll_operator(mesh.subdivide, mode=EDIT)`, `context.mode_set(OBJECT)`, and `context.info`.

- [ ] Write fake-bpy tests for poll success, poll failure, and unknown operator.
- [ ] Run `pytest tests/domains/test_context_domain.py -v` and verify failures.
- [ ] Implement server spec and add-on handler for `context.poll_operator`.
- [ ] Add `test_context_selection_mode_workflow` to `tests/test_smoke_headless.py`.
- [ ] Update roadmap current focus to subsystem 3 complete and subsystem 4 next.
- [ ] Run `pytest tests/test_smoke_headless.py -v`.
- [ ] Run `pytest`.
- [ ] Run `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'context.info','context.areas','context.set_active','context.select_objects','context.select_all','context.mode_set','context.mesh_select_mode','context.poll_operator'}; print(required <= names)"` and verify it prints `True`.
- [ ] Commit with `git commit -m "test: cover context live workflow"`.

## Final Verification

- [ ] `pytest`
- [ ] `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'context.info','context.areas','context.set_active','context.select_objects','context.select_all','context.mode_set','context.mesh_select_mode','context.poll_operator'}; print(required <= names)"`
- [ ] `git status --short --branch`
