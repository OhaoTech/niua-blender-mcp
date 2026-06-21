# Physics GUI Parity Implementation Plan

**Parent plan:** `docs/superpowers/plans/2026-06-21-layer1-gui-parity-closure.md`

**Goal:** Move the Blender Properties `PHYSICS` context from partial to covered by adding a curated `physics.*` domain for object physics stacks and force fields.

## Scope

- Server specs: `src/niua_blender_mcp/domains/physics.py`
- Add-on handlers: `blender_addon/niua_mcp_bridge/domains/physics.py`
- Fake-bpy tests: `tests/domains/test_physics.py`
- Live smoke: `tests/test_smoke_headless.py::test_physics_gui_parity_workflow`
- Audit row: `PHYSICS`

## Interfaces

- `physics.report(object)`
- `physics.add(object, type)`
- `physics.remove(object, type)`
- `physics.set(object, type, property, value)`
- `physics.field_report(object)`
- `physics.field_set(object, property, value)`

Supported `type` values: `RIGID_BODY`, `RIGID_BODY_CONSTRAINT`, `CLOTH`, `SOFT_BODY`, `FLUID`, `DYNAMIC_PAINT`, `FIELD`.

`value` is JSON-encoded for generic RNA property writes.

## Implementation Notes

- Rigid body stacks use `bpy.ops.rigidbody.object_add/remove`.
- Rigid body constraints use `bpy.ops.rigidbody.constraint_add/remove`.
- Cloth, soft body, fluid, and dynamic paint use modifier stack entries.
- Force fields use `bpy.ops.object.forcefield_toggle`; removal disables the field by setting/toggling it to `type='NONE'`.
- Reports read live RNA metadata from the backing object, modifier, settings, or field datablock.

## Tests

1. Router exposes all six `physics.*` specs.
2. Rigid body add/report/set/remove works and pushes undo only for mutations.
3. Force field add/field_report/field_set/remove works.
4. Modifier-backed physics types add/report/set/remove through object modifiers.
5. Unsupported or absent physics stacks raise structured errors without undo.
6. Live smoke adds a rigid body and force field, mutates RNA-backed settings, and reports them back.

## Verification

```bash
pytest tests/domains/test_physics.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_physics_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
```

Expected audit delta: `PHYSICS` becomes `covered`; total partial count drops by one.
