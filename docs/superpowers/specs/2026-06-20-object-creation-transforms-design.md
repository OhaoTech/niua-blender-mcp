# Object Creation / Transforms Design

Status: active direction for subsystem 4.

## Why This Subsystem Exists

The MCP currently exposes object creation and transforms through two scene-level tools:
`scene.create_object` and `scene.set_transform`. That is enough for simple smoke tests,
but it is not the way Blender users think about this work. In the GUI, creation,
duplication, deletion, naming, transforms, origins, and bounds are object operations.

Subsystem 4 creates a curated `object.*` surface so an agent can do the common object
lifecycle and transform work without falling back to raw RNA calls or GUI clicks.
The existing `scene.*` tools stay for backward compatibility, but new object work should
use the object namespace.

## Boundary

This subsystem owns:

- creating common mesh primitives and empties
- duplicating objects, including linked duplicate data
- deleting objects from the scene
- renaming objects
- reading and setting object transforms
- applying transforms
- setting object origin
- reading object bounds in local and world space

This subsystem does not own:

- collection hierarchy, parent hierarchy, view layers, and visibility restrictions
  already covered by subsystem 2
- active object, selection, modes, and operator polling already covered by subsystem 3
- mesh element editing, topology, and normals owned by subsystem 5
- curves, text, grease pencil, and non-mesh geometry owned by subsystem 6
- modifiers and geometry nodes owned by subsystem 7
- materials and shading owned by subsystem 8
- cameras, lights, rendering, compositor, and render views owned by subsystem 11
- literal GUI keyboard/mouse control owned by subsystem 12

Domain-specific creation remains with its domain. For example, subsystem 11 should add
camera and light creation/configuration instead of bloating `object.create` with every
specialized Blender object type.

## Current Evidence

Existing repo behavior:

- `scene.create_object` supports `CUBE`, `SPHERE`, `PLANE`, `CYLINDER`, `CONE`, and
  `EMPTY`, with only `name` and `location`.
- `scene.set_transform` sets location, Euler rotation, and scale.
- `io.prepare_asset` already uses `object.transform_apply` internally before export.
- No curated `object.*` tools are currently registered by `build_router()`.
- Auto-discovery means adding server/add-on `objects.py` domain modules is enough; no
  package `__init__.py` edits are needed.
- The bridge dispatcher pushes one Blender undo step after every successful mutating
  command.

Live Blender 5.1.1 checks confirmed:

- `mesh.primitive_cube_add`, `primitive_uv_sphere_add`, `primitive_plane_add`,
  `primitive_cylinder_add`, `primitive_cone_add`, `primitive_torus_add`, and
  `primitive_monkey_add` exist.
- `object.empty_add` exists and supports empty display types such as `PLAIN_AXES`,
  `ARROWS`, `CUBE`, and `SPHERE`.
- `object.transform_apply` exists with `location`, `rotation`, `scale`, `properties`,
  and `isolate_users`.
- `object.origin_set` exists with type values `GEOMETRY_ORIGIN`, `ORIGIN_GEOMETRY`,
  `ORIGIN_CURSOR`, `ORIGIN_CENTER_OF_MASS`, and `ORIGIN_CENTER_OF_VOLUME`, plus
  center values `MEDIAN` and `BOUNDS`.

## Tool Surface

Use `object.*`.

`object.create(type, name="", location=[0,0,0], rotation=[0,0,0], scale=[1,1,1], ...)`

Creates a common object primitive. Supported `type` values are `CUBE`, `SPHERE`,
`PLANE`, `CYLINDER`, `CONE`, `TORUS`, `MONKEY`, and `EMPTY`. Type-specific optional
parameters cover the common GUI controls: `size`, `radius`, `vertices`, `depth`,
`radius1`, `radius2`, `major_radius`, `minor_radius`, `major_segments`,
`minor_segments`, `end_fill_type`, `calc_uvs`, and `empty_display_type`.

`object.duplicate(object, name="", linked=False, offset=[0,0,0])`

Duplicates one object. `linked=True` shares the source data-block. `linked=False`
copies object data when Blender exposes a `copy()` method. The duplicate is linked into
the same collections as the source, or the scene root collection if the source has no
collection membership.

`object.delete(objects)`

Deletes a comma-separated object list using data-block removal with unlinking. Returns
the exact deleted names.

`object.rename(object, name)`

Renames an object and returns the updated object summary.

`object.transform_get(object)`

Returns location, Euler rotation, scale, delta transforms when available, rotation mode,
dimensions, matrix world, parent name, and collection names.

`object.transform_set(object, location?, rotation?, scale?, delta_location?,
delta_rotation?, delta_scale?, rotation_mode?)`

Sets only the provided transform fields. `rotation` means Euler rotation in radians.
`rotation_mode` is limited to Euler modes in this curated tool; quaternion and
axis-angle values remain reachable through `rna.set_property` until a later transform
expansion adds typed Vec4/axis-angle contracts.

`object.transform_apply(object, location=True, rotation=True, scale=True,
properties=True, isolate_users=False)`

Runs `bpy.ops.object.transform_apply` in object mode with the target object active and
selected.

`object.origin_set(object, type="ORIGIN_GEOMETRY", center="MEDIAN")`

Runs `bpy.ops.object.origin_set` in object mode with the target object active and
selected.

`object.bounds(object)`

Returns local bound-box corners, world bound-box corners, dimensions, and world center.
It degrades gracefully when an object type lacks a normal mesh-style bound box.

## Error Handling

- Missing object returns `not_found`.
- Empty object/name parameters return `invalid_params`.
- Unsupported creation type returns `invalid_params`.
- Invalid comma-separated object lists return `invalid_params`.
- Transform apply and origin-set poll failures return `precondition_failed`.
- Bounds on objects without a usable bound box returns an empty corner list, not an
  exception.

## Testing

Fake-bpy tests must cover:

- `object.create` dispatches each primitive family to the right Blender op and returns a
  summary.
- type-specific creation parameters are forwarded only to relevant ops.
- `object.duplicate` copies object data when `linked=False`, shares it when
  `linked=True`, links into source collections, applies offsets, and returns the new
  object.
- `object.delete` removes multiple named objects and rejects empty lists.
- `object.rename` rekeys the fake object table.
- `object.transform_get` and `object.transform_set` read/write supported transform
  fields.
- `object.transform_apply` and `object.origin_set` run inside object context and call
  the expected operators.
- `object.bounds` returns local/world corners, dimensions, and center.
- Server/add-on parity sees every new command.

Real Blender smoke must verify:

1. create a torus through `object.create`
2. set transform through `object.transform_set`
3. read transform and bounds
4. duplicate it with an offset
5. set origin
6. apply transforms
7. delete the duplicate
8. confirm all required `object.*` names are in `build_router().specs()`

## Completion Bar

Subsystem 4 is complete when an agent can perform the common object lifecycle and
transform operations that a Blender user would do from the Object menu, transform
panel, or object add menu for common primitives and empties. It is acceptable that
specialized object families, literal GUI clicks, and keyboard shortcuts remain in later
subsystems because they have their own state, editors, and quality checks.
