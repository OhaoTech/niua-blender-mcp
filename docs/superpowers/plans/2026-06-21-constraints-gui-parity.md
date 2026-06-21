# Constraints GUI Parity Implementation Plan

**Parent plan:** `docs/superpowers/plans/2026-06-21-layer1-gui-parity-closure.md`

**Goal:** Move the Blender Properties `CONSTRAINT` context from partial to covered by adding a curated `constraints.*` domain for object and pose-bone constraint stacks.

## Scope

- Server specs: `src/niua_blender_mcp/domains/constraints.py`
- Add-on handlers: `blender_addon/niua_mcp_bridge/domains/constraints.py`
- Fake-bpy tests: `tests/domains/test_constraints.py`
- Live smoke: `tests/test_smoke_headless.py::test_constraints_gui_parity_workflow`
- Audit row: `CONSTRAINT`

## Interfaces

- `constraints.list(object, owner="OBJECT")`
- `constraints.add(object, type, name="", owner="OBJECT", bone="")`
- `constraints.remove(object, name, owner="OBJECT", bone="")`
- `constraints.report(object, name="", owner="OBJECT", bone="")`
- `constraints.set(object, name, property, value, owner="OBJECT", bone="")`

`owner` accepts `OBJECT` and `BONE`. `value` is JSON-encoded for generic RNA property writes.

## Tests

1. Router exposes all five `constraints.*` specs.
2. Object constraint add/list/report/set/remove works and pushes undo only for mutations.
3. Pose-bone constraint add works through `owner="BONE"` and requires `bone`.
4. `constraints.report` emits live RNA property metadata instead of a hard-coded panel list.
5. `tests/test_parity.py` verifies server/add-on metadata parity.
6. Live smoke creates an object constraint, mutates `influence`, creates a pose-bone constraint, and reports both.

## Verification

```bash
pytest tests/domains/test_constraints.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_constraints_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
```

Expected audit delta: `CONSTRAINT` becomes `covered`; total partial count drops by one.
