# Spreadsheet GUI Parity

## Goal

Close the Layer 1 audit row for Blender's `spreadsheet` editor space.

## Interfaces

- `spreadsheet.report(object="", component="")`
- `spreadsheet.columns(object="", component="")`
- `spreadsheet.rows(object="", component="", limit=100, offset=0)`

## Notes From Blender Source

- `SpaceSpreadsheet` exposes editor state such as `show_internal_attributes`, `use_filter`, `show_only_selected`, `geometry_component_type`, `attribute_domain`, `tables`, and `row_filters`.
- The spreadsheet table values are editor runtime data, but mesh/point-cloud/curve attributes are exposed through data-block RNA.
- In headless mode, this domain reports spreadsheet area state when present and derives deterministic rows/columns from object data when no visible spreadsheet editor exists.

## Test Plan

1. Add fake-bpy tests for router registration, report payloads, columns, and paginated rows.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_spreadsheet.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage against a real mesh object.
5. Run:

   ```bash
   pytest tests/domains/test_spreadsheet.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_spreadsheet_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
