# Subsystem 8 Design: Materials / Shading / Nodes / Textures

Date: 2026-06-20
Status: planned

## Goal

Make Blender's material/shader data model visible and editable without opening the
Shader Editor:

- inspect material datablocks and object material slots
- inspect shader node trees, nodes, sockets, and links
- create common shader nodes and link sockets generically
- set scalar/vector node input defaults
- load and list image datablocks used by shader texture nodes

UV unwrapping, UV islands, image editing, painting, and texture baking are subsystem 9
or later Layer 2 work. This subsystem owns the material and shader graph substrate.

## What We Have

Existing curated tools:

- `shading.create_material(name?)`
- `shading.set_principled(material? object?, base_color?, alpha?, metallic?, roughness?, emission_strength?)`
- `shading.assign_material(object, material)`
- `shading.add_image_texture(material, image_path, target=BASE_COLOR|ROUGHNESS|NORMAL)`
- `shading.list_materials(object?)`

Current gaps:

- No `shading.report`, so the agent cannot see node trees, links, material slots,
  alpha/blend flags, or material settings before editing.
- No generic shader-node creation/linking. Only one image texture helper exists.
- No way to set arbitrary node input defaults such as color ramp stops, emission color,
  mapping values, procedural texture scale, etc. Raw RNA can do it, but no curated
  material graph API exists.
- No image datablock inventory/load surface outside `shading.add_image_texture`.

## Capability Surface

### Materials And Shader Graphs

`shading.report(material="", object="")`

Read-only. Resolves either a material by name or an object's active material. Returns:

- material name
- `use_nodes`
- material settings where present: `diffuse_color`, `blend_method`,
  `use_screen_refraction`, `show_transparent_back`
- object slot info when `object` is passed
- nodes with name, label, `type`, `bl_idname`, location, inputs, and outputs
- links as from-node/from-socket/to-node/to-socket tuples

`shading.add_node(material, type, name="")`

Adds a shader node to a material's node tree using live Blender `bl_idname` strings
such as `ShaderNodeTexNoise`, `ShaderNodeMix`, `ShaderNodeEmission`, or
`ShaderNodeTexImage`.

`shading.link_nodes(material, from_node, from_socket, to_node, to_socket)`

Creates a node link. Sockets resolve by name, identifier, or numeric index. The handler
uses Blender's `node_tree.links.new(input, output)` order.

`shading.set_node_input(material, node, input, value)`

Sets a node input default value. `value` is a JSON string so the MCP contract can remain
simple while supporting numbers, booleans, strings, and numeric arrays. The handler
coerces to the socket's current default type where possible.

Existing `shading.set_principled`, `assign_material`, `add_image_texture`, and
`list_materials` remain.

### Texture / Image Datablocks

`textures.load(path, name="")`

Loads an image datablock from disk through `bpy.data.images.load`. Optional `name`
renames the datablock after load.

`textures.list()`

Lists image datablocks: name, filepath, size, source, colorspace.

`textures.report(name)`

Reports one image datablock with the same fields.

## Error Handling

- Missing material or image returns `not_found`.
- Missing object returns `not_found`.
- Object without active material returns `precondition_failed`.
- Unsupported node type, node name, socket name, or invalid JSON value returns
  `invalid_params`.
- Image load failures return `precondition_failed` with Blender's error text.

## Testing

Fake-bpy tests cover:

- `shading.report` for material and object-slot views
- `shading.add_node` creation and naming
- `shading.link_nodes` socket resolution and link report
- `shading.set_node_input` JSON scalar/vector values
- `textures.load`, `textures.list`, and `textures.report`
- server/add-on parity

Real Blender smoke covers:

1. create a cube and material
2. set Principled base fields and inspect them with `shading.report`
3. add a `ShaderNodeTexNoise`, set its `Scale`, and link its output to Principled
   `Roughness`
4. load a tiny image file through `textures.load`, list/report it, and wire it via
   existing `shading.add_image_texture`

## Deferred

- UV map editing, texture painting, image editor UI, and baking: subsystem 9
- high-level PBR authoring recipes and material quality gates: Layer 2
- GUI shader editor gestures such as box select, node drag/drop placement, search menu,
  reroutes, frames, and pan/zoom: subsystem 12
