# Scene Tree / Outliner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build subsystem 2: a data-backed `outliner.*` MCP surface for reading and mutating Blender's logical scene tree without GUI clicks.

**Architecture:** Follow the existing two-process domain-pack pattern. Server tool specs live in `src/niua_blender_mcp/domains/outliner.py`; add-on command handlers live in `blender_addon/niua_mcp_bridge/domains/outliner.py`; fake-bpy tests drive behavior in `tests/domains/test_outliner.py`; real Blender smoke extends `tests/test_smoke_headless.py`. All logical Outliner changes use Blender data/RNA APIs, not UI Outliner operators.

**Tech Stack:** Python 3.11+, stdlib only, pytest, fake-bpy tests, real Blender 5.1 headless smoke.

## Global Constraints

- No runtime dependencies.
- Use `outliner.*` for subsystem-2 curated tools.
- Do not use GUI Outliner operators for core behavior.
- Keep active object, selection, and mode tools out of subsystem 2; subsystem 3 owns them.
- Every curated tool must have a server `ToolSpec` and matching add-on `Command`.
- Mutating tools must be marked `mutates=True` where they change scene/file state so dispatch pushes one undo step after success.
- Destructive organization changes require `force=True`.
- Run tests from repo root with `pytest`.

---

## File Map

- Create `src/niua_blender_mcp/domains/outliner.py`: server-side `ToolSpec` list for all `outliner.*` tools.
- Create `blender_addon/niua_mcp_bridge/domains/outliner.py`: add-on handlers and helpers for scene tree summaries, collection lookup, layer collection lookup, and orphan reporting.
- Create `tests/domains/test_outliner.py`: fake-bpy domain tests that mirror the handler surface and assert operator/data API behavior.
- Modify `tests/test_smoke_headless.py`: one live workflow covering collection create/move, hierarchy, visibility, view layers, and tree readback.
- Modify `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`: mark subsystem 1 complete and subsystem 2 in progress/complete after verification.

## Tool Interfaces

- `outliner.tree()`
- `outliner.describe(target, kind="AUTO")`
- `outliner.find(query, kind="ANY", limit=50)`
- `outliner.orphans()`
- `outliner.collection_create(name, parent="")`
- `outliner.collection_rename(collection, name)`
- `outliner.collection_delete(collection, force=False)`
- `outliner.object_link(object, collection)`
- `outliner.object_unlink(object, collection, force=False)`
- `outliner.object_move(object, collection)`
- `outliner.parent_set(object, parent, keep_transform=True)`
- `outliner.parent_clear(object, keep_transform=True)`
- `outliner.visibility_set(object, viewport=None, render=None, selectable=None)`
- `outliner.collection_visibility_set(collection, viewport=None, render=None, selectable=None)`
- `outliner.view_layers()`
- `outliner.view_layer_create(name)`
- `outliner.view_layer_delete(name, force=False)`
- `outliner.layer_collection_set(view_layer, collection, exclude=None, viewport=None, holdout=None, indirect_only=None)`
- `outliner.orphans_purge(force=False)`

## Task 1: Read-Only Tree, Describe, Find, Orphans

**Files:**
- Create: `tests/domains/test_outliner.py`
- Create: `blender_addon/niua_mcp_bridge/domains/outliner.py`
- Create: `src/niua_blender_mcp/domains/outliner.py`

**Interfaces:**
- Produces `outliner.tree`, `outliner.describe`, `outliner.find`, and `outliner.orphans`.
- Produces helper functions in the add-on module: `_object_summary`, `_collection_summary`, `_tree`, `_orphans`, `_find_collection`, `_find_view_layer`.

- [ ] Write fake-bpy tests for tree/describe/find/orphans.
- [ ] Run `pytest tests/domains/test_outliner.py -v` and verify failures are `unknown command`.
- [ ] Implement server specs for the four read-only tools.
- [ ] Implement add-on read handlers.
- [ ] Run `pytest tests/domains/test_outliner.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add outliner read tools"`.

## Task 2: Collections and Object Membership

**Files:**
- Modify: `tests/domains/test_outliner.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/outliner.py`
- Modify: `src/niua_blender_mcp/domains/outliner.py`

**Interfaces:**
- Adds `outliner.collection_create`, `outliner.collection_rename`, `outliner.collection_delete`, `outliner.object_link`, `outliner.object_unlink`, `outliner.object_move`.
- Collection deletion rejects non-empty collections unless `force=True`.
- Object unlink rejects unlinking the final collection unless `force=True`.

- [ ] Write fake-bpy tests for collection create/rename/delete guards.
- [ ] Write fake-bpy tests for object link/unlink/move using actual `users_collection`.
- [ ] Run `pytest tests/domains/test_outliner.py -v` and verify failures are missing commands.
- [ ] Implement server specs for collection/object membership tools.
- [ ] Implement add-on handlers using `bpy.data.collections.new/remove`, `children.link/unlink`, and `objects.link/unlink`.
- [ ] Run `pytest tests/domains/test_outliner.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add outliner collection tools"`.

## Task 3: Parent Hierarchy and Visibility Flags

**Files:**
- Modify: `tests/domains/test_outliner.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/outliner.py`
- Modify: `src/niua_blender_mcp/domains/outliner.py`

**Interfaces:**
- Adds `outliner.parent_set`, `outliner.parent_clear`, `outliner.visibility_set`, and `outliner.collection_visibility_set`.
- Parent tools reject self-parenting.
- `keep_transform=True` preserves world matrix through parent changes.
- Visibility tools require at least one flag.

- [ ] Write fake-bpy tests for parent set/clear including self-parent rejection.
- [ ] Write fake-bpy tests for object and collection visibility flag mapping.
- [ ] Run `pytest tests/domains/test_outliner.py -v` and verify failures.
- [ ] Implement server specs for parent/visibility tools.
- [ ] Implement add-on handlers using `object.parent`, `matrix_world`, `matrix_parent_inverse`, `hide_viewport`, `hide_render`, and `hide_select`.
- [ ] Run `pytest tests/domains/test_outliner.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add outliner hierarchy controls"`.

## Task 4: View Layers, Layer Collections, Orphan Purge

**Files:**
- Modify: `tests/domains/test_outliner.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/outliner.py`
- Modify: `src/niua_blender_mcp/domains/outliner.py`

**Interfaces:**
- Adds `outliner.view_layers`, `outliner.view_layer_create`, `outliner.view_layer_delete`, `outliner.layer_collection_set`, and `outliner.orphans_purge`.
- Deleting the last view layer is rejected.
- Deleting a view layer requires `force=True`.
- Layer collection setter requires at least one flag.
- Orphan purge always requires `force=True`.

- [ ] Write fake-bpy tests for view-layer listing/create/delete guards.
- [ ] Write fake-bpy tests for layer collection flag mapping.
- [ ] Write fake-bpy tests for orphan purge force guard and purge call.
- [ ] Run `pytest tests/domains/test_outliner.py -v` and verify failures.
- [ ] Implement server specs for view-layer/orphan tools.
- [ ] Implement add-on handlers using `scene.view_layers.new/remove`, recursive `LayerCollection` lookup, and orphan purge API/operator fallback.
- [ ] Run `pytest tests/domains/test_outliner.py tests/test_parity.py -v`.
- [ ] Commit with `git commit -m "feat: add outliner view layer tools"`.

## Task 5: Live Smoke, Roadmap, Full Verification

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

**Interfaces:**
- Live smoke verifies the high-risk data API workflow in real Blender:
  `outliner.collection_create` → `outliner.object_move` → `outliner.parent_set` →
  `outliner.parent_clear` → `outliner.visibility_set` →
  `outliner.collection_visibility_set` → `outliner.view_layer_create` →
  `outliner.layer_collection_set` → `outliner.view_layer_delete` → `outliner.tree`.

- [ ] Add live smoke test `test_outliner_scene_tree_workflow`.
- [ ] Update the roadmap current focus from subsystem 1 to subsystem 2 status.
- [ ] Run `pytest tests/test_smoke_headless.py -v`.
- [ ] Run `pytest`.
- [ ] Run `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'outliner.tree','outliner.collection_create','outliner.object_move','outliner.parent_set','outliner.view_layers','outliner.layer_collection_set'}; print(required <= names)"` and verify it prints `True`.
- [ ] Commit with `git commit -m "test: cover outliner live workflow"`.

## Final Verification

- [ ] `pytest`
- [ ] `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'outliner.tree','outliner.describe','outliner.find','outliner.orphans','outliner.collection_create','outliner.collection_rename','outliner.collection_delete','outliner.object_link','outliner.object_unlink','outliner.object_move','outliner.parent_set','outliner.parent_clear','outliner.visibility_set','outliner.collection_visibility_set','outliner.view_layers','outliner.view_layer_create','outliner.view_layer_delete','outliner.layer_collection_set','outliner.orphans_purge'}; print(required <= names)"`
- [ ] `git status --short --branch`
