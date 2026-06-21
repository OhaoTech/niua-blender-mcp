# Volume GUI Parity

## Goal

Close the Layer 1 audit row for Blender's `VOLUME` object data type.

## Interfaces

- `volume.create_empty(name="", location=[0,0,0])`
- `volume.import(path, name="")`
- `volume.list()`
- `volume.report(name_or_object)`
- `volume.set(name_or_object, property, value)`

## Notes From Blender Source

- Object type: `OB_VOLUME` / RNA object type `VOLUME`
- Data-block: `Volume`
- Empty add operator: `object.volume_add`
- OpenVDB import operator: `object.volume_import`
- Properties panel spans the volume data-block plus nested `display`, `render`, and `grids` RNA objects. `volume.set` accepts dotted paths such as `display.density` and `render.space`.

## Test Plan

1. Add fake-bpy tests for router registration, create/list/report, dotted property set, import operator dispatch, data-block lookup, and precondition failures.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_volume.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage using `volume.create_empty`.
5. Run:

   ```bash
   pytest tests/domains/test_volume.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_volume_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
