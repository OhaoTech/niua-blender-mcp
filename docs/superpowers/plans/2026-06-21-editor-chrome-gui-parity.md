# Editor Chrome GUI Parity

## Goal

Close Layer 1 audit rows for Blender's `info`, `topbar`, and `statusbar` editor spaces.

## Interfaces

- `info.report()`
- `info.messages(limit=100)`
- `topbar.report()`
- `topbar.command_search(query, limit=20)`
- `statusbar.report()`

## Notes From Blender Source

- Info editor operators exist under `bpy.ops.info`, but the report list itself is not exposed as stable RNA in this Blender build.
- Topbar search is interactive (`bpy.ops.wm.search_operator`); the MCP surface returns deterministic searchable operator metadata instead of opening a modal search UI.
- Statusbar mostly reflects context and scene statistics; use `scene.statistics(view_layer)` where available.

## Test Plan

1. Add fake-bpy tests for router registration, report payloads, unavailable Info message list, command search, and scene statistics.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_info.py tests/domains/test_topbar.py tests/domains/test_statusbar.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage for all five commands.
5. Run:

   ```bash
   pytest tests/domains/test_info.py tests/domains/test_topbar.py tests/domains/test_statusbar.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_info_topbar_statusbar_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
