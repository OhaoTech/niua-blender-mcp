# Curves / Text / Grease Pencil / Non-Mesh Geometry Design

Status: active direction for subsystem 6.

## Why This Subsystem Exists

The MCP can now create common mesh primitives, edit mesh topology, and transform
objects. Blender artists also build with non-mesh geometry: curves for paths/tubes,
text objects for labels and typography, NURBS surfaces, metaballs, and grease pencil
objects. Today those families are only reachable through raw RNA or generic operators.

Subsystem 6 adds a curated non-mesh geometry surface so an agent can create, inspect,
adjust, and convert the main non-mesh object families without using GUI menus.

## Boundary

This subsystem owns:

- curve primitive creation and curve data settings
- text object creation and text data settings
- NURBS surface primitive creation
- metaball primitive creation
- grease pencil object creation and reporting
- common non-mesh data reports
- conversion of supported non-mesh objects to mesh

This subsystem does not own:

- mesh topology editing, already covered by subsystem 5
- object transforms and object lifecycle, already covered by subsystem 4
- materials and shading, owned by subsystem 8
- UV/image workflows, owned by subsystem 9
- animation/rigging, owned by subsystem 10
- grease pencil stroke drawing, frame/layer animation, onion skinning, and drawing-tool
  workflows; those need deeper 2D drawing semantics and/or GUI/event parity
- viewport mouse drawing, modal handles, curve point dragging, and text editing through
  keyboard events; subsystem 12 owns GUI parity

## Namespace

Use `geometry.*`.

An umbrella namespace is deliberate here. Blender stores curves, text, surfaces,
metaballs, and grease pencil as different object/data types, but this subsystem is the
non-mesh geometry layer. Splitting into `curve.*`, `text.*`, `surface.*`, and
`grease_pencil.*` would add boilerplate before the tool surface is large enough to need
separate packs.

## Current Evidence

Existing repo behavior:

- No curated tools currently expose curve, text, metaball, surface, or grease pencil
  creation/configuration.
- `object.create` intentionally covers only common mesh primitives and empties.
- `outliner.orphans` already lists zero-user `curves`, `cameras`, `lights`, etc.
- `core/capture.scene_bbox` already includes object types `MESH`, `CURVE`, `SURFACE`,
  `META`, and `FONT`.
- `session.checkpoint` can snapshot object data blocks including mesh/curve-style data
  through `obj.data.copy()`.

Live Blender 5.1.1 checks confirmed:

- Curve creation operators exist:
  `curve.primitive_bezier_curve_add`, `curve.primitive_bezier_circle_add`,
  `curve.primitive_nurbs_curve_add`, `curve.primitive_nurbs_circle_add`, and
  `curve.primitive_nurbs_path_add`.
- Text creation uses `object.text_add`.
- Metaball creation uses `object.metaball_add(type=BALL|CAPSULE|PLANE|ELLIPSOID|CUBE)`.
- Surface creation operators exist:
  `surface.primitive_nurbs_surface_curve_add`,
  `surface.primitive_nurbs_surface_circle_add`,
  `surface.primitive_nurbs_surface_surface_add`,
  `surface.primitive_nurbs_surface_cylinder_add`,
  `surface.primitive_nurbs_surface_sphere_add`, and
  `surface.primitive_nurbs_surface_torus_add`.
- Grease pencil creation uses `object.grease_pencil_add` with types
  `EMPTY`, `STROKE`, `MONKEY`, `LINEART_SCENE`, `LINEART_COLLECTION`, and
  `LINEART_OBJECT`.
- `object.convert(target=MESH, keep_original=...)` converts curves/text to meshes
  headlessly. With `keep_original=False`, the active object remains the same name and
  becomes `MESH`; with `keep_original=True`, Blender creates a mesh copy and makes that
  copy active.
- Curve-like data blocks expose stable properties:
  `bevel_depth`, `bevel_resolution`, `extrude`, `resolution_u`,
  `render_resolution_u`, `dimensions`, `fill_mode`, and `use_fill_caps`.
- Text data additionally exposes `body`, `align_x`, `align_y`, `size`, `space_line`,
  `offset_x`, and `offset_y`.
- Metaball data exposes `elements`; grease pencil data exposes `layers`.

## Tool Surface

`geometry.create_curve(type, name="", radius=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`

Creates a curve primitive. `type` is `BEZIER`, `BEZIER_CIRCLE`, `NURBS_CURVE`,
`NURBS_CIRCLE`, or `NURBS_PATH`.

`geometry.create_text(name="", body="Text", align_x="LEFT", align_y="TOP_BASELINE",
size=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`

Creates a text object and immediately sets its core text fields.

`geometry.create_surface(type, name="", radius=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`

Creates a NURBS surface primitive. `type` is `CURVE`, `CIRCLE`, `SURFACE`, `CYLINDER`,
`SPHERE`, or `TORUS`.

`geometry.create_metaball(type="BALL", name="", radius=1.0, location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`

Creates a metaball primitive.

`geometry.create_grease_pencil(type="EMPTY", name="", radius=1.0, use_in_front=False,
location=[0,0,0], rotation=[0,0,0], scale=[1,1,1])`

Creates a grease pencil object. This is object/data creation only; stroke authoring is
deferred.

`geometry.report(object)`

Reports object type, data-block type, transform summary, material count, curve/text
settings where present, spline counts, metaball element counts, and grease pencil layer
counts. It is read-only.

`geometry.set_curve(object, bevel_depth?, bevel_resolution?, extrude?, resolution_u?,
render_resolution_u?, dimensions?, fill_mode?, use_fill_caps?)`

Sets shared curve/text/surface curve-data geometry fields. It accepts `CURVE`, `FONT`,
and `SURFACE` objects and rejects unsupported object types.

`geometry.set_text(object, body?, align_x?, align_y?, size?, space_line?, offset_x?,
offset_y?)`

Sets text-only fields and rejects non-`FONT` objects.

`geometry.convert_to_mesh(object, name="", keep_original=False)`

Runs Blender's conversion operator with the object active and selected. Returns the
converted mesh summary. If `name` is provided, the resulting mesh object is renamed.

## Error Handling

- Missing object returns `not_found`.
- Unsupported object type for curve/text setters returns `precondition_failed`.
- Unsupported create enum values are rejected server-side by `ToolSpec` validation.
- Conversion poll failures return `precondition_failed`.
- Report degrades gracefully for object families that do not expose a given field.

## Testing

Fake-bpy tests must cover:

- server/add-on parity for every `geometry.*` command
- curve creation operator dispatch, naming, transform kwargs, and report output
- text creation plus text field updates
- surface, metaball, and grease pencil creation dispatch
- `geometry.set_curve` updates only provided fields and rejects unsupported object types
- `geometry.set_text` updates only provided fields and rejects non-text objects
- `geometry.convert_to_mesh` uses `ctx.ensure(active=obj, mode="OBJECT", select=[obj])`,
  calls `object.convert(target="MESH", keep_original=...)`, renames the active converted
  object when requested, and returns a mesh report

Real Blender smoke must verify:

1. create and report a Bezier circle curve
2. set curve bevel/extrude/resolution fields
3. create and update a text object
4. create and report a NURBS surface, metaball, and grease pencil object
5. convert the curve to mesh and verify the resulting object type is `MESH`
6. confirm all `geometry.*` names are in `build_router().specs()`

## Completion Bar

Subsystem 6 is complete when an agent can create, inspect, adjust, and convert the main
non-mesh geometry object families from code: curves, text, surfaces, metaballs, and
grease pencil object data. It is acceptable that curve point editing, grease-pencil
stroke authoring, and GUI-style text/handle interactions remain deferred because those
require richer editor semantics and, in some cases, the GUI event layer.
