# Context / Selection / Modes Design

Status: approved direction for subsystem 3.

## Why This Subsystem Exists

Blender operators do not only need parameters. They also need context: an active
object, a selection, a mode, sometimes an editor area, and often a matching object type.
The repo already has an internal context resolver (`ctx.ensure`) that temporarily sets
active object, selection, mode, and area override for domain handlers. That internal
resolver makes mesh/uv/rigging operators work, but the MCP does not yet expose a
curated way for an agent to inspect or deliberately control the same state.

Subsystem 3 turns Blender context into an explicit MCP surface. This lets the agent ask
"what is active?", "what is selected?", "what mode am I in?", set that state directly,
and test whether an operator would poll in a proposed context before invoking it.

## Boundary

This subsystem owns:

- active object
- selected objects
- object-mode selection actions
- interaction mode switching (`OBJECT`, `EDIT`, `POSE`, sculpt/paint modes where Blender
  supports them for the active object)
- mesh edit selection mode (`VERT`, `EDGE`, `FACE`, and common combinations)
- available editor areas for context override
- operator poll checks in current or proposed context

This subsystem does not own:

- logical collection hierarchy or view-layer restrictions (subsystem 2)
- object creation and transforms (subsystem 4)
- mesh element editing beyond select-mode state (subsystem 5)
- actual GUI keyboard/mouse events (subsystem 12)

## Namespace

Use `context.*`.

The repo already has a Python module named `niua_mcp_bridge.context`, but domain modules
live under `niua_mcp_bridge.domains.*`, so a `domains/context.py` pack is unambiguous.
Tool names should say `context` because active object, selected objects, mode, and area
override are all Blender context state.

## Current Evidence

Existing internals:

- `ctx.ensure(active=..., mode=..., select=..., area="VIEW_3D")` temporarily sets
  active/selection/mode/area and restores it.
- `ctx.check_poll(op)` turns operator poll failures into clean `precondition_failed`
  errors.
- `rna.call_operator` already uses `ctx.ensure(active/mode/select)` for generic
  operator invocation.

Live Blender 5.1.1 checks confirmed:

- `bpy.context.view_layer.objects.active` is the active object slot.
- `object.select_set(bool)` and `object.select_get()` are the object selection API.
- `bpy.context.selected_objects` reports current selected objects.
- `bpy.ops.object.mode_set(mode=...)` supports:
  `OBJECT`, `EDIT`, `POSE`, `SCULPT`, `VERTEX_PAINT`, `WEIGHT_PAINT`,
  `TEXTURE_PAINT`, `PARTICLE_EDIT`, `EDIT_GPENCIL`, `SCULPT_GREASE_PENCIL`,
  `PAINT_GREASE_PENCIL`, `WEIGHT_GREASE_PENCIL`, `VERTEX_GREASE_PENCIL`,
  and `SCULPT_CURVES`.
- In edit mode, `bpy.context.mode` reports typed modes such as `EDIT_MESH`, while
  `context.object.mode` reports `EDIT`.
- `bpy.context.tool_settings.mesh_select_mode` is the vertex/edge/face selection mode.
- In headless Blender there may be no `VIEW_3D` area; the existing resolver must keep
  skipping temp override when no area exists.

## Tool Surface

`context.info()`

Returns current context state:

- scene, view layer, workspace when available
- active object summary
- selected object summaries
- context mode and active object mode
- mesh select mode
- available editor areas

`context.areas()`

Lists windows, screens, areas, and window regions available for context override. In
headless mode this returns an empty list and `has_view3d=false`.

`context.set_active(object, select=True)`

Sets the active object. When `select=True`, also selects that object. Rejects hidden or
unselectable objects with `precondition_failed`.

`context.select_objects(objects, action="REPLACE", active="")`

Updates object selection. `objects` is a comma-separated string. `action` is one of
`REPLACE`, `ADD`, `REMOVE`, or `TOGGLE`. When `active` is provided, it must be one of
the selected objects after the action.

`context.select_all(action="DESELECT")`

Object-level select all. `action` is `SELECT`, `DESELECT`, or `INVERT`. It acts on scene
objects that support `select_set`.

`context.mode_set(mode, object="", select=True)`

Switches Blender interaction mode. If `object` is provided, make it active first; when
`select=True`, select it before switching. Mode switching uses `bpy.ops.object.mode_set`
and surfaces poll/runtime failures as `precondition_failed`.

`context.mesh_select_mode(mode)`

Sets mesh edit selection mode. `mode` is one of `VERT`, `EDGE`, `FACE`, `VERT_EDGE`,
`VERT_FACE`, `EDGE_FACE`, `VERT_EDGE_FACE`. It updates
`bpy.context.tool_settings.mesh_select_mode`.

`context.poll_operator(idname, object="", mode="", select="")`

Resolves a Blender operator and returns whether its `poll()` passes in the current or
proposed context. `select` is a comma-separated object list. This tool does not invoke
the operator and does not push undo.

## Error Handling

- Missing object returns `not_found`.
- Invalid empty string parameters return `invalid_params`.
- Selecting hidden or unselectable objects returns `precondition_failed`.
- Setting active to a hidden or unselectable object returns `precondition_failed`.
- Mode-set poll/runtime failures return `precondition_failed`.
- `context.poll_operator` returns `{"ok": false, "available": false, "reason": ...}`
  instead of raising for failed poll; it raises `not_found` only when the operator id
  does not exist.
- Headless area absence is not an error; `context.areas` reports no areas and
  `context.poll_operator` still works for operators that do not require a GUI area.

## Testing

Fake-bpy tests must cover:

- info shape
- area listing with and without windows
- set active with selection side effect and hidden/unselectable guards
- select actions: replace/add/remove/toggle/select all/deselect/invert
- mode set with active object and clean poll/runtime failure
- mesh select mode mapping
- poll operator success, poll failure, and unknown operator
- server/add-on parity

Real Blender smoke must verify:

1. create two objects
2. set active
3. replace/add/toggle selection
4. switch to edit mode and back to object mode
5. set mesh select mode
6. poll `mesh.subdivide` in edit context
7. inspect `context.info`

## Completion Bar

Subsystem 3 is complete when an agent can inspect and deliberately set active object,
object selection, interaction mode, mesh select mode, and operator-poll context without
depending on GUI clicks. It is acceptable that literal keyboard shortcuts, viewport box
selection, and mouse hit-testing remain deferred to subsystem 12.
