# Tracking / Clip Editor GUI Parity

## Goal

Close the Layer 1 audit row for Blender's `clip` editor space.

## Interfaces

- `tracking.report()`
- `tracking.clip_load(path, name="")`
- `tracking.clips()`
- `tracking.marker_report(clip)`
- `tracking.track_report(clip)`

## Notes From Blender Source

- Editor space: `space_clip`
- Data-block: `MovieClip`
- Open operator: `clip.open`; data API: `bpy.data.movieclips.load(path)`
- UI panels inspect `clip.tracking.settings`, `clip.tracking.tracks`, active tracks, markers, camera, stabilization, objects, graph, and dopesheet state.
- This Layer 1 slice is read-heavy. It loads clips and reports clip/tracking state without solving motion or mutating tracks.

## Test Plan

1. Add fake-bpy tests for router registration, clip load/list/report, track report, marker report, and missing path/clip errors.
2. Watch the focused command fail before implementation:

   ```bash
   pytest tests/domains/test_tracking.py tests/test_parity.py -v
   ```

3. Add server `ToolSpec`s and add-on handlers.
4. Add live headless smoke coverage by generating a tiny PNG and loading it as a MovieClip.
5. Run:

   ```bash
   pytest tests/domains/test_tracking.py tests/test_parity.py -v
   pytest tests/test_smoke_headless.py::test_tracking_gui_parity_workflow -v
   python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
   pytest -q
   git diff --check
   ```
