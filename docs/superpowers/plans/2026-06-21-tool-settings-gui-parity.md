# Tool Settings GUI Parity Plan

## Goal

Close the Layer 1 audit row for the Properties editor `TOOL` context by exposing active workspace tools and `bpy.context.tool_settings` through curated MCP tools.

## Interfaces

- `tool.active(area_type="VIEW_3D", mode="")`
- `tool.set(idname, area_type="VIEW_3D", mode="")`
- `tool.settings(area_type="VIEW_3D", mode="")`
- `tool.setting_get(path)`
- `tool.setting_set(path, value)`

## Implementation Notes

- Resolve active tools through `context.workspace.tools.from_space_*` accessors.
- Switch tools with `bpy.ops.wm.tool_set_by_id(name=..., space_type=...)`; never call `WorkSpaceTool.setup` directly because it is unsafe in background Blender.
- Resolve `tool.setting_*` paths relative to `bpy.context.tool_settings`.
- Use RNA metadata for reporting and read-only checks.
- Mutating calls rely on dispatch for the single undo step.

## Verification

```bash
pytest tests/domains/test_tool.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_tool_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
pytest -q
git diff --check
```
