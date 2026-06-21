# Sequencer GUI Parity Implementation Plan

**Parent plan:** `docs/superpowers/plans/2026-06-21-layer1-gui-parity-closure.md`

**Goal:** Move `STRIP`, `STRIP_MODIFIER`, and editor space `sequencer` from partial to covered by adding a curated `sequencer.*` domain.

## Scope

- Server specs: `src/niua_blender_mcp/domains/sequencer.py`
- Add-on handlers: `blender_addon/niua_mcp_bridge/domains/sequencer.py`
- Fake-bpy tests: `tests/domains/test_sequencer.py`
- Live smoke: `tests/test_smoke_headless.py::test_sequencer_gui_parity_workflow`
- Audit rows: `STRIP`, `STRIP_MODIFIER`, editor space `sequencer`

## Interfaces

- `sequencer.report()`
- `sequencer.strip_add(type, name="", frame_start=1, channel=1, path="")`
- `sequencer.strip_remove(name)`
- `sequencer.strip_set(name, property, value)`
- `sequencer.modifiers(name)`
- `sequencer.modifier_add(name, type, modifier_name="")`
- `sequencer.modifier_set(name, modifier, property, value)`
- `sequencer.modifier_remove(name, modifier)`

`value` is JSON-encoded for generic strip/modifier RNA property writes.

## Implementation Notes

- Use `scene.sequence_editor_create().strips` on Blender 5.1; fall back to legacy `sequences` if needed.
- Create effect strips through `strips.new_effect(..., length=...)`, not `frame_end`.
- Add strip modifiers through `bpy.ops.sequencer.strip_modifier_add` under a `SEQUENCE_EDITOR` context. The data API `strip.modifiers.new()` crashes in the current headless Blender 5.1 build, so live headless smoke covers strips while fake-bpy covers modifier behavior.

## Tests

1. Router exposes all eight `sequencer.*` specs.
2. Strip add/report/set/remove works and pushes undo only for mutations.
3. Strip reports include live RNA metadata.
4. Modifier add/list/set/remove works in fake-bpy through the operator-backed path.
5. Missing strips/modifiers fail before undo.
6. Live smoke creates a color strip, mutates timing/channel/name, reports it, and removes it.

## Verification

```bash
pytest tests/domains/test_sequencer.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_sequencer_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
```

Expected audit delta: `STRIP`, `STRIP_MODIFIER`, and editor space `sequencer` become `covered`; total partial count drops by three.
