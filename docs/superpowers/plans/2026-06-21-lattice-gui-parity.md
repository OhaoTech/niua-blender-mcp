# Lattice GUI Parity Plan

## Goal

Close the Layer 1 audit row for Blender lattice object-data coverage with curated tools for creating, inspecting, editing lattice data, and mutating lattice points.

## Interfaces

- `lattice.create(name="", location=[0,0,0])`
- `lattice.report(object)`
- `lattice.set(object, property, value)`
- `lattice.point_set(object, index, co_deform)`
- `lattice.convert_to_mesh(object, name="")`

## Implementation Notes

- Create lattices through `bpy.ops.object.add(type="LATTICE")`, matching the View3D Add menu.
- Report lattice data through live RNA, including `points_u/v/w`, interpolation modes, `use_outside`, and a bounded lattice-point sample.
- Mutate lattice points through `LatticePoint.co_deform`.
- `object.convert(target="MESH")` does not convert lattice objects in Blender 5.1 background mode; expose `lattice.convert_to_mesh` as a structured precondition failure when Blender leaves the object as a lattice.

## Verification

```bash
pytest tests/domains/test_lattice.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_lattice_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on none
pytest -q
git diff --check
```
