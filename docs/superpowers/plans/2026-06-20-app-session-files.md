# App / Session / Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete subsystem 1 by exposing engine-neutral file IO plus app/session/file lifecycle tools.

**Architecture:** Keep the existing two-process contract: server `SPECS` in `src/niua_blender_mcp/domains/`, add-on `COMMANDS` in `blender_addon/niua_mcp_bridge/domains/`, parity tested. File and app operations are implemented with Blender's `bpy.ops.wm`, `bpy.data`, `bpy.context`, and `addon_utils`. Dangerous file operations require explicit `force=True`.

**Tech Stack:** Python 3.11+, stdlib only, pytest, fake-bpy tests, real Blender smoke tests.

## Global Constraints

- No runtime dependencies.
- No game-engine or orchestrator names in code-facing tool names or summaries.
- Use `ctx.bpy` only in add-on handlers.
- Every new curated tool must have a server `ToolSpec` and matching add-on `Command`.
- Mutating tools must flow through dispatch so undo is pushed after successful handler execution where Blender undo is meaningful. App/file/preference lifecycle operations (`app.file_*`, workspace switching, add-on toggles, preference saves) intentionally do not push Blender undo steps because they mutate session/file/application state rather than undoable scene data.
- File paths for open/save/export tools must be absolute unless the tool explicitly documents otherwise.
- Run tests from repo root with `pytest`.

---

## Task 1: Neutral Engine-Free IO Surface

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/io.py`
- Modify: `src/niua_blender_mcp/domains/io.py`
- Modify: `tests/domains/test_io.py`
- Modify: `tests/test_smoke_headless.py`

**Interfaces:**
- `io.export(path, format="AUTO", objects="", apply_modifiers=True, y_up=True)`
- `io.prepare_asset(object, path, format="AUTO", apply_transforms=True, apply_modifiers=True, y_up=True)`
- Remove curated `io.export_gltf` and `io.prepare_godot`.

- [ ] Write failing tests that call `io.export` with GLB selection/export flags and `io.prepare_asset`.
- [ ] Run focused IO tests and verify failures.
- [ ] Implement generic export routing and prepare_asset.
- [ ] Update live smoke tests from old tool names to generic tool names.
- [ ] Run `pytest tests/domains/test_io.py -v` and commit.

## Task 2: App Info and File Lifecycle

**Files:**
- Create: `blender_addon/niua_mcp_bridge/domains/app.py`
- Create: `src/niua_blender_mcp/domains/app.py`
- Create: `tests/domains/test_app.py`

**Interfaces:**
- `app.info()`
- `app.file_new(force=False)`
- `app.file_open(path, force=False)`
- `app.file_save(path="")`
- `app.file_save_as(path)`
- `app.file_save_copy(path)`
- `app.file_revert(force=False)`

- [ ] Write fake-bpy tests for info, force guards, and operator calls.
- [ ] Run focused app tests and verify failures.
- [ ] Implement add-on handlers and server specs.
- [ ] Run focused app tests and parity tests, then commit.

## Task 3: Undo, Redo, Workspaces, Add-ons, Preferences

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/app.py`
- Modify: `src/niua_blender_mcp/domains/app.py`
- Modify: `tests/domains/test_app.py`

**Interfaces:**
- `app.undo()`
- `app.redo()`
- `app.workspaces()`
- `app.workspace_set(name)`
- `app.addons()`
- `app.addon_enable(module)`
- `app.addon_disable(module)`
- `app.preferences_summary()`
- `app.preferences_save()`

- [ ] Write fake-bpy tests for each command.
- [ ] Run focused app tests and verify failures.
- [ ] Implement handlers and specs.
- [ ] Run focused app tests and full parity, then commit.

## Task 4: Live Smoke and Docs

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/PLAN.md`

**Interfaces:**
- Live smoke should verify `app.info`, `app.file_save_copy`, `app.file_save_as`, `app.file_open`, `app.undo`, `app.redo`, and `app.workspaces` where available.

- [ ] Add live smoke tests.
- [ ] Run `pytest tests/test_smoke_headless.py -v`.
- [ ] Update docs status for subsystem 1.
- [ ] Run full `pytest`.
- [ ] Commit.

## Final Verification

- [ ] `pytest`
- [ ] `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; print({'app.info','app.file_open','app.file_save','app.undo','app.workspaces','io.export','io.prepare_asset'} <= names)"`
- [ ] `git status --short --branch`
