# Point Cloud GUI Parity

## Goal

Close the Layer 1 audit row for Blender's `POINTCLOUD` object data type.

## Interfaces

- `pointcloud.list()`
- `pointcloud.report(name_or_object)`
- `pointcloud.set(name_or_object, property, value)`
- `pointcloud.attributes(name_or_object)`

## Notes From Blender Source

- Object type: `OB_POINTCLOUD` / RNA object type `POINTCLOUD`
- Data-block: `PointCloud`
- Add operator: `object.pointcloud_random_add`, which creates 400 points with `position` and `radius` attributes
- RNA properties expose `points`, `materials`, `attributes`, `color_attributes`, and ID-level writable fields such as `name` and `use_fake_user`

## Test Plan

1. Add fake-bpy tests for router registration, list/report, attribute report, set, and read-only precondition failures.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_pointcloud.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage using `object.pointcloud_random_add`.
5. Run:

   ```bash
   pytest tests/domains/test_pointcloud.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_pointcloud_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
