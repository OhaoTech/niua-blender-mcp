# Object Creation / Transforms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build subsystem 4: a curated `object.*` MCP surface for common object creation, lifecycle, transforms, origins, and bounds.

**Architecture:** Follow the existing domain-pack pattern. Server specs live in `src/niua_blender_mcp/domains/objects.py`; add-on handlers live in `blender_addon/niua_mcp_bridge/domains/objects.py`; fake-bpy tests live in `tests/domains/test_objects.py`; live smoke extends `tests/test_smoke_headless.py`. Keep legacy `scene.create_object` and `scene.set_transform` unchanged for backward compatibility.

**Tech Stack:** Python 3.11+, stdlib only, pytest, fake-bpy tests, real Blender 5.1.1 headless smoke.

## Global Constraints

- No runtime dependencies.
- Use `object.*` for subsystem-4 curated tools.
- Do not implement collection hierarchy, parenting, view layers, active object, selection, or modes here; subsystems 2 and 3 own those.
- Do not implement mesh element editing here; subsystem 5 owns it.
- Do not implement curves, cameras, lights, armatures, materials, or UI keyboard/mouse here; later subsystems own those.
- Every curated tool must have a server `ToolSpec` and matching add-on `Command`.
- Mutating tools must be marked `mutates=True` and `feedback="viewport"`.
- Run tests from repo root with `pytest`.

---

## Tool Interfaces

- `object.create(type, name="", location=[0,0,0], rotation=[0,0,0], scale=[1,1,1], size=2.0, radius=1.0, vertices=32, depth=2.0, radius1=1.0, radius2=0.0, major_radius=1.0, minor_radius=0.25, major_segments=48, minor_segments=12, end_fill_type="NGON", calc_uvs=True, empty_display_type="PLAIN_AXES")`
- `object.duplicate(object, name="", linked=False, offset=[0,0,0])`
- `object.delete(objects)`
- `object.rename(object, name)`
- `object.transform_get(object)`
- `object.transform_set(object, location?, rotation?, scale?, delta_location?, delta_rotation?, delta_scale?, rotation_mode?)`
- `object.transform_apply(object, location=True, rotation=True, scale=True, properties=True, isolate_users=False)`
- `object.origin_set(object, type="ORIGIN_GEOMETRY", center="MEDIAN")`
- `object.bounds(object)`

## Task 1: Server Specs and Read Helpers

**Files:**
- Create: `tests/domains/test_objects.py`
- Create: `src/niua_blender_mcp/domains/objects.py`
- Create: `blender_addon/niua_mcp_bridge/domains/objects.py`

**Interfaces:**
- Produces server specs for `object.transform_get` and `object.bounds`.
- Produces add-on read handlers for `object.transform_get` and `object.bounds`.
- Add-on helper `_object_state(obj) -> dict` returns name, type, transforms, rotation mode, dimensions, parent, collections, and matrix world.
- Add-on helper `_bounds_state(obj) -> dict` returns object, dimensions, local corners, world corners, and center.

- [ ] Write fake-bpy tests that assert `build_router().specs()` contains `object.transform_get` and `object.bounds`.
- [ ] Write fake-bpy tests for `object.transform_get` and `object.bounds`.
- [ ] Run `pytest tests/domains/test_objects.py -v` and verify failures are missing module/spec/unknown command failures.
- [ ] Add `src/niua_blender_mcp/domains/objects.py` with the read `ToolSpec` definitions.
- [ ] Add `blender_addon/niua_mcp_bridge/domains/objects.py` with read helpers and read commands only.
- [ ] Run `pytest tests/domains/test_objects.py tests/test_parity.py -v` and verify the read tests pass.
- [ ] Commit with `git commit -m "feat: add object read specs"`.

## Task 2: Object Creation

**Files:**
- Modify: `tests/domains/test_objects.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/objects.py`

**Interfaces:**
- Implements `object.create`.
- Adds the `object.create` server spec.
- Supported types: `CUBE`, `SPHERE`, `PLANE`, `CYLINDER`, `CONE`, `TORUS`, `MONKEY`, `EMPTY`.
- Creation dispatch uses Blender operators and returns `_object_state(created_object)`.

- [ ] Write fake-bpy tests for `CUBE`, `TORUS`, and `EMPTY` creation, including forwarded parameters and returned state.
- [ ] Run `pytest tests/domains/test_objects.py::test_create_dispatches_supported_primitives -v` and verify it fails because `object.create` is unimplemented.
- [ ] Implement `_vec`, `_created`, `_create_kwargs`, and `create_object`.
- [ ] Register `Command("object.create", create_object, mutates=True, feedback="viewport")`.
- [ ] Run `pytest tests/domains/test_objects.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add object creation tool"`.

## Task 3: Lifecycle Tools

**Files:**
- Modify: `tests/domains/test_objects.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/objects.py`

**Interfaces:**
- Implements `object.duplicate`, `object.delete`, and `object.rename`.
- Adds the `object.duplicate`, `object.delete`, and `object.rename` server specs.
- `_parse_objects(ctx, raw) -> list[Any]` parses comma-separated names and rejects empty lists.
- `object.duplicate` copies object data when `linked=False`, shares data when `linked=True`, links into source collections or the scene root collection, applies offset to location, and returns `_object_state(new_object)`.
- `object.delete` removes each object via `bpy.data.objects.remove(obj, do_unlink=True)` and returns `{"deleted": names, "count": len(names)}`.
- `object.rename` renames an object and returns `_object_state(obj)`.

- [ ] Write fake-bpy tests for unlinked duplicate data copy, linked duplicate data sharing, collection linking, and offset.
- [ ] Write fake-bpy tests for deleting multiple objects and rejecting an empty object list.
- [ ] Write fake-bpy tests for rename rekeying the fake object table.
- [ ] Run the new tests and verify they fail on unimplemented commands.
- [ ] Implement lifecycle helpers and handlers.
- [ ] Register lifecycle commands with `mutates=True` and `feedback="viewport"`.
- [ ] Run `pytest tests/domains/test_objects.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add object lifecycle tools"`.

## Task 4: Transform Mutation Tools

**Files:**
- Modify: `tests/domains/test_objects.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/objects.py`

**Interfaces:**
- Implements `object.transform_set`, `object.transform_apply`, and `object.origin_set`.
- Adds the `object.transform_set`, `object.transform_apply`, and `object.origin_set` server specs.
- Euler rotation modes: `XYZ`, `XZY`, `YXZ`, `YZX`, `ZXY`, `ZYX`.
- `object.transform_apply` and `object.origin_set` use `ctx.ensure(active=obj, mode="OBJECT", select=[obj])`, call `ctx.check_poll`, then run the Blender operator.

- [ ] Write fake-bpy tests for `object.transform_set` updating only provided fields.
- [ ] Write fake-bpy tests for `object.transform_apply` operator arguments and context usage.
- [ ] Write fake-bpy tests for `object.origin_set` operator arguments and context usage.
- [ ] Run the new tests and verify they fail on unimplemented commands.
- [ ] Implement transform mutation handlers.
- [ ] Register transform mutation commands with `mutates=True` and `feedback="viewport"`.
- [ ] Run `pytest tests/domains/test_objects.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add object transform tools"`.

## Task 5: Live Smoke, Roadmap, Final Verification

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

**Interfaces:**
- Adds `test_object_lifecycle_transform_workflow`.
- Updates roadmap current focus to subsystem 4 complete and subsystem 5 next.

- [ ] Add a live smoke test that creates a torus, sets transform, reads transform and bounds, duplicates with offset, sets origin, applies transforms, deletes the duplicate, and verifies the duplicate is gone.
- [ ] Run `pytest tests/test_smoke_headless.py -v`.
- [ ] Update the roadmap with subsystem 4 completion notes.
- [ ] Run `pytest`.
- [ ] Run `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'object.create','object.duplicate','object.delete','object.rename','object.transform_get','object.transform_set','object.transform_apply','object.origin_set','object.bounds'}; print(required <= names)"` and verify it prints `True`.
- [ ] Run `git status --short --branch`.
- [ ] Commit with `git commit -m "test: cover object live workflow"`.

## Final Verification

- [ ] `pytest`
- [ ] `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'object.create','object.duplicate','object.delete','object.rename','object.transform_get','object.transform_set','object.transform_apply','object.origin_set','object.bounds'}; print(required <= names)"`
- [ ] `git status --short --branch`
