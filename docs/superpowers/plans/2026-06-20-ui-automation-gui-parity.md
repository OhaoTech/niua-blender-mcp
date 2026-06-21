# Implementation Plan: Subsystem 12 UI Automation / GUI Parity Layer

Date: 2026-06-20
Status: completed

## Global Constraints

- Follow TDD: write tests first, run targeted red, implement, run green, commit.
- Keep the UI layer honest: return availability metadata for foreground-only behavior;
  do not pretend background Blender can receive physical mouse/keyboard events.
- Preserve `feedback.*` as the visual scene-observation layer.
- Keep server specs and add-on commands in parity.
- `ui.operator_invoke` is mutating and must rely on dispatcher undo after success.
- Use `ctx.bpy` in handlers; no top-level `bpy` imports.

## File Map

- Create: `src/niua_blender_mcp/domains/ui.py`
- Create: `blender_addon/niua_mcp_bridge/domains/ui.py`
- Create: `tests/domains/test_ui.py`
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

## Task 1: UI State And Window Topology

Interfaces:

- `ui.state`
- `ui.windows`

Steps:

1. Create fake-bpy UI tests with a window manager, screens, areas, regions, geometry,
   screenshot/redraw operators, and app background state.
2. Add failing tests for router exposure, `ui.state`, and `ui.windows`.
3. Run targeted red tests.
4. Add server specs in `src/niua_blender_mcp/domains/ui.py`.
5. Add add-on handlers in `blender_addon/niua_mcp_bridge/domains/ui.py`.
6. Run:
   - `pytest tests/domains/test_ui.py tests/test_parity.py -v`
7. Commit:
   - `git commit -m "feat: add ui state reports"`

## Task 2: Area-Aware Operator Poll And Invoke

Interfaces:

- `ui.operator_poll`
- `ui.operator_invoke`

Steps:

1. Extend fake-bpy UI tests with mesh/object operators, RNA properties, active object,
   selection, mode switching, and `temp_override` recording.
2. Add failing tests for:
   - polling with a selected `VIEW_3D` area and returned target metadata
   - unavailable result when `require_area=true` and the target area is missing
   - invoking an operator with JSON args, active/mode/select hints, and one undo push
   - unknown operators and bad JSON errors
3. Run targeted red tests.
4. Implement shared helpers for operator resolution, target resolution, temp overrides,
   and JSON parsing. Reuse the existing RNA arg validator from `rna_exec`.
5. Run:
   - `pytest tests/domains/test_ui.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add area aware ui operators"`

## Task 3: UI Screenshot And Redraw Availability

Interfaces:

- `ui.screenshot`
- `ui.redraw`

Steps:

1. Extend fake-bpy UI tests with screenshot/redraw operators whose `poll()` can pass or
   fail.
2. Add failing tests for:
   - screenshot unavailable when poll fails
   - screenshot success writes/returns file metadata in the fake environment
   - redraw unavailable when poll fails
   - redraw success returns applied operator metadata
3. Run targeted red tests.
4. Implement screenshot/redraw wrappers with clean unavailable results.
5. Run:
   - `pytest tests/domains/test_ui.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add ui screenshot and redraw tools"`

## Task 4: Live Smoke, Roadmap, Final Verification

Steps:

1. Add `test_ui_automation_gui_parity_workflow` to `tests/test_smoke_headless.py`.
2. Update roadmap:
   - subsystem 12 complete
   - all 12 Layer-1 subsystems implemented
   - remaining literal OS mouse/keyboard automation deferred to a separate foreground
     desktop adapter
3. Run:
   - `pytest tests/test_smoke_headless.py::test_ui_automation_gui_parity_workflow -v`
   - `pytest tests/test_smoke_headless.py -v`
   - `pytest`
   - `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'ui.state','ui.windows','ui.operator_poll','ui.operator_invoke','ui.screenshot','ui.redraw'}; print(required <= names); print(sorted(required - names))"`
   - `git status --short --branch`
4. Commit:
   - `git commit -m "test: cover ui automation workflow"`
