# Speaker GUI Parity

## Goal

Close the Layer 1 audit row for Blender's `SPEAKER` object data type.

## Interfaces

- `speaker.create(name="", location=[0,0,0])`
- `speaker.list()`
- `speaker.report(name)`
- `speaker.set(name, property, value)`

## Notes From Blender Source

- Object type: `OB_SPEAKER` / RNA object type `SPEAKER`
- Data-block: `Speaker`
- Speaker properties panels expose sound, mute, volume, pitch, distance, and cone settings.
- `object.speaker_add` creates a speaker plus an NLA sound strip. In the local Blender 5.1.1 background build it aborts while creating that empty sound strip, so `speaker.create` uses `object.add(type="SPEAKER")`, which creates the same speaker object/data-block without the crashing NLA side effect.

## Test Plan

1. Add fake-bpy tests for router registration, create/list/report, writable property set, sound pointer assignment, and non-speaker preconditions.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_speaker.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage using `speaker.create`.
5. Run:

   ```bash
   pytest tests/domains/test_speaker.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_speaker_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
