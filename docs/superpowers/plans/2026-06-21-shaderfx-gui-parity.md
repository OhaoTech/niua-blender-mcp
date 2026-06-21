# Shader Effects GUI Parity Plan

## Goal

Close the Layer 1 audit rows for the Properties editor `SHADERFX` context and the `shaderfx` object data surface by exposing the Grease Pencil shader effect stack through curated MCP tools.

## Interfaces

- `shaderfx.list(object)`
- `shaderfx.types()`
- `shaderfx.add(object, type, name="")`
- `shaderfx.remove(object, name)`
- `shaderfx.report(object, name="")`
- `shaderfx.set(object, name, property, value)`

## Implementation Notes

- Use real Blender shader effect identifiers such as `FX_BLUR`, `FX_COLORIZE`, and `FX_WAVE`.
- Shader effects are object stack data on Grease Pencil objects (`object.shader_effects`).
- Mutating stack operations must run in object mode with the target object active/selected.
- Use RNA metadata for reports and editable property checks.
- Use Blender's `object.shaderfx_add` and `object.shaderfx_remove` operators for GUI parity.

## Verification

```bash
pytest tests/domains/test_shaderfx.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_shaderfx_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
pytest -q
git diff --check
```
