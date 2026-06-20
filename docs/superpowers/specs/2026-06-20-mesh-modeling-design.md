# Mesh Modeling Design

Status: active direction for subsystem 5.

## Why This Subsystem Exists

The current mesh domain proves the edit-mode path works: the agent can extrude, bevel,
inset, subdivide, recalculate normals, shade, and read `mesh.report`. That is enough for
simple geometry changes, but it still depends on implicit Blender selection state. A GUI
artist can deliberately select vertices, edges, and faces before deleting, dissolving,
merging, filling, or converting topology. The MCP needs that same deterministic selection
floor before mesh editing can be trusted.

Subsystem 5 expands `mesh.*` from "a few edit operators" into a deterministic mesh
modeling surface: inspect selection, select elements by index, run common topology edit
operators, and keep the generated/reflection path available for the long tail.

## Boundary

This subsystem owns:

- mesh element selection state for vertices, edges, and faces
- selection reports and index-based selection mutation
- common edit-mode topology operators: delete, dissolve, merge, remove doubles,
  tri/quad conversion, fill, and shade/normal operations
- analytic mesh reports for topology and selection counts
- operator-backed edit actions that are headless-safe and not dependent on mouse input

This subsystem does not own:

- object creation and transforms, already covered by subsystem 4
- collection hierarchy, parenting, view layers, active object, and object selection,
  already covered by subsystems 2 and 3
- UV editing, owned by subsystem 9
- modifiers and geometry nodes, owned by subsystem 7
- sculpting, grease pencil, curves, text, and non-mesh geometry, owned by subsystem 6 or
  later domain specs
- viewport mouse picking, knife drawing, box/lasso selection, gizmos, and UI event
  shortcuts, owned by subsystem 12

Complex or view-driven mesh operators remain reachable through `rna.call_operator` and
the generated `modeling.*` catalog where they poll in the current context. Curated
`mesh.*` tools are reserved for stable, deterministic operations an agent can call
without a real viewport event stream.

## Current Evidence

Existing repo behavior:

- Curated `mesh.*` currently exposes:
  `mesh.extrude`, `mesh.bevel`, `mesh.inset`, `mesh.subdivide`,
  `mesh.recalc_normals`, `mesh.shade_smooth`, and `mesh.report`.
- `ctx.ensure(active=obj, mode="EDIT", select=[obj])` already gives edit-mode operators
  a reliable active object, selected object, mode switch, and restore.
- `ctx.check_poll(op)` turns Blender poll failures into clean `precondition_failed`
  errors.
- Layer-2 craft verbs already compose raw mesh ops:
  `model.retopo_quads`, `model.bevel_edges`, and `model.recess_panels`.
- The generated manifest includes hidden `modeling.*` tools for some raw mesh operators:
  subdivide, bevel, extrude_region_move, inset, loopcut_slide, merge,
  tris_convert_to_quads, quads_convert_to_tris, normals_make_consistent, and
  remove_doubles.
- The full manifest lists many more `mesh.*` operators, but only a subset is safe to
  curate before GUI/event parity exists.

Live Blender 5.1.1 checks confirmed:

- `mesh.select_all(action=TOGGLE|SELECT|DESELECT|INVERT)` exists.
- `mesh.select_mode(type=VERT|EDGE|FACE, action=DISABLE|ENABLE|TOGGLE)` exists.
- `mesh.delete(type=VERT|EDGE|FACE|EDGE_FACE|ONLY_FACE)` exists.
- `mesh.dissolve_verts`, `mesh.dissolve_edges`, `mesh.dissolve_faces`, and
  `mesh.dissolve_limited` exist.
- `mesh.merge(type=CENTER|CURSOR|COLLAPSE|FIRST|LAST, uvs=...)` exists.
- `mesh.remove_doubles(threshold=..., use_centroid=..., use_unselected=...,
  use_sharp_edge_from_normals=...)` exists.
- `mesh.tris_convert_to_quads` and `mesh.quads_convert_to_tris` exist.
- `mesh.edge_face_add` and `mesh.fill(use_beauty=...)` exist.
- Setting `mesh.polygons[index].select=True` in object mode, then entering edit mode and
  calling `mesh.delete(type="FACE")`, works headlessly and reduced a cube from 6 faces to
  5.

## Tool Surface

Extend `mesh.*`.

### Selection Tools

`mesh.selection_report(object="")`

Returns selected vertex, edge, and face indices plus counts. It must read mesh data in
object mode so it works headlessly and does not depend on viewport overlays.

`mesh.select_all(object="", action="SELECT")`

Runs Blender's mesh element select-all operator in edit mode. Valid actions are
`SELECT`, `DESELECT`, `INVERT`, and `TOGGLE`.

`mesh.select_by_index(object, mode, indices, action="REPLACE")`

Selects mesh elements by zero-based index. `mode` is `VERT`, `EDGE`, or `FACE`.
`indices` is a comma-separated string. `action` is `REPLACE`, `ADD`, `REMOVE`, or
`TOGGLE`. The handler sets mesh data selection flags in object mode, updates
`context.tool_settings.mesh_select_mode`, and returns `mesh.selection_report`.

### Topology Edit Tools

`mesh.delete(object="", type="VERT")`

Deletes selected mesh elements in edit mode. Valid types are `VERT`, `EDGE`, `FACE`,
`EDGE_FACE`, and `ONLY_FACE`.

`mesh.dissolve(object="", type="EDGES", use_verts=False, angle_limit=0.0872665,
use_dissolve_boundaries=False)`

Dissolves selected geometry. `type` is `VERTS`, `EDGES`, `FACES`, or `LIMITED`.
`LIMITED` uses `mesh.dissolve_limited`; the others use the matching dissolve operator.

`mesh.merge(object="", type="CENTER", uvs=True)`

Merges selected vertices using Blender's merge operator.

`mesh.remove_doubles(object="", threshold=0.0001)`

Merges duplicate vertices using Blender's `mesh.remove_doubles`.

`mesh.tris_to_quads(object="", face_threshold=40.0, shape_threshold=40.0)`

Converts selected triangles to quads. Threshold inputs are degrees; the handler converts
them to radians for Blender.

`mesh.quads_to_tris(object="", quad_method="BEAUTY", ngon_method="BEAUTY")`

Converts selected quads/n-gons to triangles.

`mesh.fill(object="", beauty=True)`

Fills selected edges/faces using `mesh.fill(use_beauty=beauty)`.

`mesh.edge_face_add(object="")`

Creates an edge or face from selected vertices/edges using `mesh.edge_face_add`.

Existing tools remain unchanged:

- `mesh.extrude`
- `mesh.bevel`
- `mesh.inset`
- `mesh.subdivide`
- `mesh.recalc_normals`
- `mesh.shade_smooth`
- `mesh.report`

## Error Handling

- Missing object returns `not_found`.
- No active object returns `precondition_failed`.
- Non-mesh object returns `precondition_failed`.
- Empty index strings return `invalid_params`.
- Non-integer or out-of-range indices return `invalid_params`.
- Unsupported enum values are rejected server-side by `ToolSpec` validation.
- Operator poll failures return `precondition_failed`.

## Testing

Fake-bpy tests must cover:

- server/add-on parity for every new `mesh.*` command
- selection report with selected vertices/edges/faces
- `mesh.select_all` operator call and undo behavior
- `mesh.select_by_index` replace/add/remove/toggle behavior for vertices, edges, and faces
- `mesh.delete` operator call and return shape
- `mesh.dissolve` dispatch to verts/edges/faces/limited operators
- `mesh.merge`, `mesh.remove_doubles`, `mesh.tris_to_quads`,
  `mesh.quads_to_tris`, `mesh.fill`, and `mesh.edge_face_add` operator calls
- clean invalid index handling

Real Blender smoke must verify:

1. create a cube through `object.create`
2. select one face by index with `mesh.select_by_index`
3. verify `mesh.selection_report` sees exactly that face
4. delete selected face with `mesh.delete(type="FACE")`
5. verify `mesh.report` face count changed from 6 to 5
6. on a separate mesh, run tri/quad conversion, remove doubles, merge/fill path where
   headless polling allows it
7. confirm all new `mesh.*` names are in `build_router().specs()`

## Completion Bar

Subsystem 5 is complete when an agent can explicitly inspect and set mesh element
selection and run the stable, headless-safe topology edit operations that normally live
in Blender's Mesh menu. It is acceptable that view-dependent tools such as interactive
knife cuts, mouse picking, box/lasso selection, and modal viewport gestures remain
deferred to subsystem 12 because those require GUI/event parity, not just mesh data and
operators.
