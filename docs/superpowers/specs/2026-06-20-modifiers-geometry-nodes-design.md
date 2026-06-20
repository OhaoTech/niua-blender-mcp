# Subsystem 7 Design: Modifiers / Geometry Nodes

Date: 2026-06-20
Status: planned

## Goal

Make Blender's non-destructive stack controllable without the GUI:

- inspect the full modifier stack with enough detail to make decisions
- add any modifier type Blender exposes, not a small hardcoded subset
- edit common stack visibility flags and modifier properties
- reorder, duplicate, apply, and remove modifiers
- create and inspect a Geometry Nodes modifier
- author a minimal Geometry Nodes graph through data APIs: add nodes and create links

This is not the GUI event layer. Dragging stack rows, clicking disclosure triangles, node
editor pan/zoom/marquee selection, and keyboard-driven node editor interaction stay in
subsystem 12. The data model those GUI actions mutate belongs here.

## What We Have

Existing curated tools:

- `modifiers.add(object?, type, name?)`
- `modifiers.set(object?, name, property, value)`
- `modifiers.apply(object?, name)`
- `modifiers.remove(object?, name)`
- `modifiers.list(object?)`

Existing generated/reflection fallback:

- `capabilities.search/describe/invoke`
- generated tools for a few modifier operators such as `modifiers.modifier_add` and
  `modifiers.modifier_apply`
- raw `rna.*` get/set/call escape hatches

Current gaps:

- `modifiers.add` hardcodes eight modifier types, while Blender 5.1 exposes many more,
  including `NODES`.
- `modifiers.list` only returns name/type/show_viewport; the agent cannot see stack
  order, render/edit/cage flags, expansion state, execution timing, or node group info.
- There is no curated way to list supported modifier types from the running Blender.
- There is no curated stack reorder or duplicate/copy command.
- Geometry Nodes is only reachable through raw RNA/operators. There is no domain-level
  create/report/add-node/link-node workflow.

## Capability Surface

### Modifier Stack

`modifiers.types()`

Read-only. Returns live modifier type enum items from
`bpy.types.Modifier.bl_rna.properties["type"].enum_items`.

`modifiers.add(object?, type, name?)`

`type` is a string, not a fixed enum. Blender is the source of truth. Unsupported types
return `precondition_failed` from `obj.modifiers.new`.

`modifiers.list(object?)`

Read-only stack report. Each modifier item includes:

- `index`, `name`, `type`
- `show_viewport`, `show_render`, `show_in_editmode`, `show_on_cage`, `show_expanded`
- `is_active` where Blender exposes it
- `execution_time` where Blender exposes it
- `node_group` name for Geometry Nodes modifiers
- a shallow `properties` map for scalar/string/bool fields that are safe to serialize

`modifiers.set_visibility(object?, name, viewport?, render?, editmode?, cage?, expanded?)`

Writes common stack visibility flags only when provided.

`modifiers.move(object?, name, index)`

Uses `bpy.ops.object.modifier_move_to_index(modifier=name, index=index)` inside
`ctx.ensure(active=obj, mode="OBJECT", select=[obj])`.

`modifiers.copy(object?, name, new_name?)`

Uses `bpy.ops.object.modifier_copy(modifier=name)`, then optionally renames the copied
modifier. Returns the copied modifier report.

Existing `set`, `apply`, and `remove` remain.

### Geometry Nodes

`geometry_nodes.create_modifier(object, name="")`

Uses `bpy.ops.node.new_geometry_nodes_modifier()` with the object active and selected.
This matches Blender's own default Geometry Nodes button: it creates a `NODES`
modifier, a node group, group input/output nodes, geometry interface sockets, and a
passthrough geometry link.

`geometry_nodes.report(object, modifier="")`

Reports the selected or first `NODES` modifier:

- modifier name
- node group name
- interface sockets
- nodes with names, labels, `bl_idname`, locations, inputs, and outputs
- links as from-node/from-socket/to-node/to-socket tuples

`geometry_nodes.add_node(object, modifier="", type, name="")`

Adds a node to the modifier's node group using `node_group.nodes.new(type=<type>)`.
The node type string is live Blender's `bl_idname`; unsupported types return
`invalid_params`.

`geometry_nodes.link(object, modifier="", from_node, from_socket, to_node, to_socket)`

Creates a node link by resolving node names and socket names or numeric indices.
Existing links are left intact unless Blender rejects the link.

## Error Handling

- Missing object returns `not_found`.
- Missing modifier returns `not_found`.
- No active object for optional-object tools returns `precondition_failed`.
- Unsupported modifier types return `precondition_failed`.
- Unsupported node types, missing nodes, and missing sockets return `invalid_params`.
- Operator poll failures return `precondition_failed`.

## Testing

Fake-bpy tests cover:

- live type-list shape using fake enum items
- adding non-hardcoded modifier types such as `TRIANGULATE` and `NODES`
- detailed `modifiers.list` serialization
- visibility flag updates
- move/copy operator dispatch and stack mutation
- `geometry_nodes.create_modifier` creates a `NODES` modifier and group
- `geometry_nodes.report` returns nodes, interface sockets, and links
- `geometry_nodes.add_node` and `geometry_nodes.link`
- server/add-on parity

Real Blender smoke covers:

1. create a cube
2. list modifier types and assert `NODES`, `BEVEL`, and `TRIANGULATE` are present
3. add a non-hardcoded modifier (`TRIANGULATE`), move it, set visibility, copy it
4. create a Geometry Nodes modifier and assert group input/output nodes and a geometry
   passthrough link exist
5. add one extra Geometry Nodes node and verify it appears in the report

## Deferred

- GUI node editor interaction: subsystem 12
- complex group interface socket creation/removal/reordering
- simulation zones, bake panels, viewer items, and named attribute/bake panels
- high-level procedural modeling recipes using Geometry Nodes; those belong to Layer 2
  craft verbs once this substrate is stable
