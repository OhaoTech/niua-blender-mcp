# Light Probe GUI Parity Plan

## Goal

Close the Layer 1 audit row for Blender light probe object-data coverage with curated tools for creating, listing, reporting, and editing light probes.

## Interfaces

- `lightprobe.create(type, name="", location=[0,0,0])`
- `lightprobe.list()`
- `lightprobe.report(name)`
- `lightprobe.set(name, property, value)`

## Implementation Notes

- Use `bpy.ops.object.lightprobe_add(type=...)`, matching the Add menu.
- Support Blender 5.1 light probe types `SPHERE`, `PLANE`, and `VOLUME`.
- Report live RNA from the light probe data-block so type-specific properties are visible.
- Resolve `name` as the light probe object name.
- Mutating property writes parse JSON and enforce RNA read-only flags.

## Verification

```bash
pytest tests/domains/test_lightprobe.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_lightprobe_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
pytest -q
git diff --check
```
