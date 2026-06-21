# Script Space GUI Parity

## Goal

Close the final Layer 1 audit row for Blender's `script` editor space.

## Interfaces

- `script.report()`
- `script.paths()`
- `script.run_file(path)`
- `script.reload()`

## Notes From Blender Source

- `SPACE_SCRIPT` is marked deprecated in the source, but still registers script operators.
- The runtime script operators are `script.python_file_run` and `script.reload`; Blender also exposes `script.execute_preset` from Python UI modules.
- Running files and reloading scripts can execute local Python, so MCP keeps these behind the same explicit `allow_python` trust gate used by `system.execute_python`.

## Test Plan

1. Add fake-bpy tests for router registration, report payloads, script paths, and gated file execution.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_script.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage for report/path discovery.
5. Run:

   ```bash
   pytest tests/domains/test_script.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_script_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on partial
   pytest -q
   git diff --check
   ```
