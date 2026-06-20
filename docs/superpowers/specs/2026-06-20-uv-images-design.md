# Subsystem 9 Design: UV / Images

Date: 2026-06-20
Status: planned

## Goal

Make Blender's UV layout workflow controllable without the UV Editor GUI:

- inspect UV layers, active layer, UV presence, island count, and seam state
- create, delete, and activate UV layers
- mark/clear seams deterministically by edge index
- run existing unwrap/project/pack/scale operators on a known full-face selection
- export a UV layout image to disk

Image datablock load/list/report for shader textures was completed in subsystem 8 as
`textures.*`. This subsystem owns UV layout and UV image export. Texture painting,
image editing, and baking remain later work.

## What We Have

Existing curated tools:

- `uv.smart_unwrap(object?, angle_limit=66, island_margin=0)`
- `uv.unwrap(object?, method=ANGLE_BASED|CONFORMAL, island_margin=0)`
- `uv.cube_project(object?, cube_size=1)`
- `uv.sphere_project(object?)`
- `uv.pack_islands(object?, margin=0.001)`
- `uv.average_islands_scale(object?)`
- `uv.report(object?)`

Current strengths:

- Operator calls already run through `ctx.ensure(active=obj, mode="EDIT", select=[obj])`.
- Handlers select all faces before UV operators, avoiding stale selection surprises.
- `uv.report` already includes layer names, active layer, `has_uvs`, and island count
  when bmesh is available.

Current gaps:

- No UV layer create/delete/set-active tools.
- No seam report or seam mutation tools.
- No UV layout image export.
- No direct way to inspect which edge indices are seams before unwrap.

## Capability Surface

`uv.layers(object?)`

Read-only. Returns layer names, active layer, active index, and count.

`uv.layer_create(object?, name="UVMap", do_init=True)`

Creates a UV layer through `mesh.uv_layers.new(name=<name>, do_init=<bool>)` and returns
the updated layer report.

`uv.layer_set_active(object?, name)`

Sets `mesh.uv_layers.active` by name and returns the updated layer report.

`uv.layer_delete(object?, name)`

Removes a UV layer by name and returns the updated layer report.

`uv.seams(object?)`

Read-only. Returns `seam_edges` as edge indices where `edge.use_seam` is true and
`edge_count`.

`uv.set_seams(object?, edges, action=SET|ADD|REMOVE|CLEAR)`

Mutates `mesh.edges[i].use_seam`. `edges` is a comma-separated list of integer edge
indices. `CLEAR` ignores `edges` and clears all seams. Returns the seam report.

`uv.export_layout(object?, path, size=1024, opacity=0.25, export_all=True, modified=False, format=AUTO|PNG|SVG|EPS)`

Runs `bpy.ops.uv.export_layout(filepath=path, size=(size, size), opacity=opacity,
export_all=export_all, modified=modified, mode=format)` with the mesh active in edit
mode and all faces selected. `AUTO` infers format from `.png`, `.svg`, or `.eps`.
Returns path, format, and file size. PNG export requires Blender's GPU offscreen drawing,
so headless background verification uses SVG.

Existing unwrap/project/pack/report tools remain.

## Error Handling

- Missing object returns `not_found`.
- Non-mesh object or no active object returns `precondition_failed`.
- Missing UV layer returns `not_found`.
- Bad edge index strings or out-of-range edge indices return `invalid_params`.
- Export operator poll/export failures return `precondition_failed`.

## Testing

Fake-bpy tests cover:

- server/add-on parity for new tools
- UV layer create/set-active/delete
- seam report and set/add/remove/clear actions
- invalid edge indices
- export-layout operator dispatch with edit-mode context and select-all

Real Blender smoke covers:

1. create cube
2. create and activate a `Lightmap` UV layer
3. mark two seam edges, read them back, remove one, clear all
4. run smart unwrap and pack
5. export UV layout SVG and assert the file exists and is non-empty

## Deferred

- UV Editor GUI selection/pinning/transform gestures: subsystem 12
- texture painting and image editor operations
- bake workflows and texel-density quality gates: Layer 2 / later subsystem work
