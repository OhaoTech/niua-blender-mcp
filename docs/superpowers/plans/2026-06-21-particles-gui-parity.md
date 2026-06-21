# Particles GUI Parity Implementation Plan

**Parent plan:** `docs/superpowers/plans/2026-06-21-layer1-gui-parity-closure.md`

**Goal:** Move the Blender Properties `PARTICLES` context from partial to covered by adding a curated `particles.*` domain for object particle systems and their settings.

## Scope

- Server specs: `src/niua_blender_mcp/domains/particles.py`
- Add-on handlers: `blender_addon/niua_mcp_bridge/domains/particles.py`
- Fake-bpy tests: `tests/domains/test_particles.py`
- Live smoke: `tests/test_smoke_headless.py::test_particles_gui_parity_workflow`
- Audit row: `PARTICLES`

## Interfaces

- `particles.systems(object)`
- `particles.add(object, name="")`
- `particles.remove(object, name)`
- `particles.report(object, name="")`
- `particles.set(object, name, property, value)`

`value` is JSON-encoded. `property` resolves first against the particle system, then against `particle_system.settings`, and also accepts dotted paths such as `settings.count`.

## Tests

1. Router exposes all five `particles.*` specs.
2. Add/list/remove uses `object.particle_system_add/remove` and pushes undo only for mutations.
3. Reports include live RNA metadata from both the particle system and `ParticleSettings`.
4. `particles.set` can mutate settings fields like `count` and `frame_start`.
5. Missing particle systems fail before undo.
6. Live smoke adds a particle system, mutates count and timing, reports them back, then removes it.

## Verification

```bash
pytest tests/domains/test_particles.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_particles_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
```

Expected audit delta: `PARTICLES` becomes `covered`; total partial count drops by one.
