# Text Editor GUI Parity

## Goal

Close the Layer 1 audit rows for Blender's `text` editor space and contribute to the `script` editor-space row.

## Interfaces

- `text.list()`
- `text.create(name, body="")`
- `text.open(path, name="")`
- `text.read(name)`
- `text.write(name, body)`
- `text.append(name, body)`
- `text.save(name, path="")`
- `text.remove(name)`

## Notes From Blender Source

- Editor space: `space_text`
- Data-block: `Text`
- Operators include `text.new`, `text.open`, `text.save`, `text.save_as`, `text.unlink`, `text.run_script`, and editing commands.
- RNA/data API exposes `bpy.data.texts.new`, `bpy.data.texts.load`, `Text.as_string`, `Text.from_string`, `Text.write`, `Text.clear`, `Text.filepath`, `Text.is_dirty`, `Text.is_modified`, `Text.is_in_memory`, `Text.use_module`, and `Text.indentation`.

## Test Plan

1. Add fake-bpy tests for router registration, create/list/read/write/append/save/remove, open from disk, and missing path/text failures.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_text.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage for create/write/append/save/open/remove.
5. Run:

   ```bash
   pytest tests/domains/test_text.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_text_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
