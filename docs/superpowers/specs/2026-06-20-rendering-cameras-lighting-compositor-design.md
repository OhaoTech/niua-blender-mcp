# Subsystem 11 Design: Rendering / Cameras / Lighting / Compositor

Date: 2026-06-20
Status: planned

## Goal

Make Blender's render setup controllable without the Camera, Light, Render Properties,
World, or Compositor GUIs:

- create, list, inspect, edit, and activate cameras
- create, list, inspect, and edit lights
- inspect and edit render settings
- render a still image to disk in background Blender
- inspect and edit world color/strength
- enable and inspect the compositor node tree
- add compositor nodes and link sockets by name or index

`feedback.*` remains the agent's visual observation layer. Subsystem 11 owns authored
scene render state and file-output rendering.

## What We Have

Existing related tools:

- `feedback.capture`, `feedback.capture_views`, and `feedback.turntable` render temporary
  diagnostic views and gracefully degrade when no GPU/display is available.
- `rna.*` and `capabilities.*` expose the long tail of render, camera, light, and node
  operators.
- `object.*` can transform existing objects, but it intentionally does not create camera
  or light datablocks.

Current gaps:

- No curated camera creation/list/report/set-active tools.
- No curated light creation/list/report/set tools.
- No render settings report or mutation surface.
- No real still-render file output tool.
- No world settings surface.
- No compositor node-tree report/add/link surface.

## Capability Surface

### Cameras

`camera.create(name?, location?, rotation?, lens=50, type=PERSP, ortho_scale=6, clip_start=0.1, clip_end=1000, active=True)`

Uses `bpy.ops.object.camera_add`, applies common camera data properties, optionally makes
the camera `scene.camera`, and returns a camera report.

`camera.list()`

Read-only. Lists scene camera objects and the active scene camera.

`camera.report(camera?)`

Read-only. Reports the named camera, or the active scene camera when omitted.

`camera.set(camera, lens?, type?, ortho_scale?, clip_start?, clip_end?)`

Sets only provided camera data properties and returns the camera report.

`camera.set_active(camera)`

Sets `scene.camera` and returns `camera.list`.

### Lights

`light.create(type=POINT|SUN|SPOT|AREA, name?, location?, rotation?, energy=10, color?, size?, spot_size?, spot_blend?)`

Uses `bpy.ops.object.light_add`, applies common light data properties, and returns a light
report.

`light.list()`

Read-only. Lists scene light objects.

`light.report(light?)`

Read-only. Reports one light when named, otherwise all scene lights.

`light.set(light, energy?, color?, size?, spot_size?, spot_blend?)`

Sets only provided light data properties and returns the light report.

### Render And World

`render.settings()`

Read-only. Reports engine, filepath, resolution, image format, film transparency, and
active camera.

`render.set_settings(engine?, filepath?, resolution_x?, resolution_y?, image_format?, transparent?)`

Sets only provided render settings and returns `render.settings`.

`render.still(path, camera?, engine?, resolution_x?, resolution_y?, image_format="PNG")`

Temporarily applies provided render overrides, runs `bpy.ops.render.render(write_still=True)`,
restores previous scene settings, and returns path, format, and file size. A live Blender
5.1 background probe verified Workbench still rendering works headless.

`world.report()`

Read-only. Reports scene world name, color, `use_nodes`, and Background node strength
when available.

`world.set(color?, strength?)`

Sets world color directly. When `strength` is provided, enables world nodes and writes the
Background node Strength input.

### Compositor

`compositor.enable(enable=True)`

Sets `scene.use_nodes`, creating Blender's default compositor tree when enabling, then
returns `compositor.report`.

`compositor.report()`

Read-only. Reports `scene.use_nodes`, node names/types/locations/sockets, and links.

`compositor.add_node(type, name?)`

Enables compositor nodes, adds `scene.node_tree.nodes.new(type=<type>)`, optionally
renames the node, and returns the new node plus current report data.

`compositor.link(from_node, from_socket, to_node, to_socket)`

Creates a compositor node link by node name plus socket name or numeric index.

## Error Handling

- Missing objects, cameras, lights, nodes, sockets, or worlds return `not_found` or
  `invalid_params` depending on whether the identifier is scene data or a node-tree lookup.
- Wrong object type returns `precondition_failed`.
- Unsupported camera/light/node/render engine values let Blender validate and return
  `invalid_params` or `precondition_failed` with detail.
- Render operator failures return `precondition_failed` and leave prior scene settings
  restored.

## Testing

Fake-bpy tests cover:

- server/add-on parity for all new tools
- camera create/list/report/set/set-active
- light create/list/report/set
- render settings mutation and still-render file output/restoration
- world report/set
- compositor enable/report/add-node/link

Real Blender smoke covers:

1. create a camera and set it active
2. create and edit an area light
3. set render settings and world strength
4. enable compositor, add one node, and verify node-tree report
5. render a small Workbench PNG still to a temporary path

## Deferred

- Viewport camera gizmo interaction, light gizmo manipulation, preview render region, and
  compositor editor GUI gestures stay in subsystem 12.
- Production render presets, color management look design, multi-pass EXR pipelines,
  cryptomatte, render farm execution, and lighting artistry belong to Layer 2 craft verbs
  once this data/control substrate is stable.
