# Project and API GUI Parity

## Goal

Close the Layer 1 audit rows for Blender's `project` and `api` editor spaces.

## Interfaces

- `project.report()`
- `project.files()`
- `project.settings()`
- `api.report()`
- `api.search(query, limit=20)`

## Notes From Blender Source

- `space_project.py` exposes project state, project auto-save preferences, project save/open operators, and `.blender_project/project.toml`.
- Some Blender builds expose `bpy.data.project`; others expose only the project operators and project config files. The MCP surface reports both without assuming the runtime project datablock exists.
- `space_api` is the editor registration/API source surface, not a normal visible Python UI in this build. The MCP API surface reports and searches live `bpy.ops`/`bpy.types` metadata.

## Test Plan

1. Add fake-bpy tests for router registration, project report/files/settings, API report, and API search.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_project.py tests/domains/test_api.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage for project config discovery and API search.
5. Run:

   ```bash
   pytest tests/domains/test_project.py tests/domains/test_api.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_project_api_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
