# Implementation Plan: Subsystem 7 Modifiers / Geometry Nodes

Date: 2026-06-20
Status: completed

## Global Constraints

- Follow TDD: write failing tests first, run the targeted red command, implement, run green,
  commit each task.
- Keep server specs and add-on commands in parity; `tests/test_parity.py` must pass after
  each task.
- Mutating tools must be `mutates=True` so dispatch pushes undo after successful handlers.
- Use `ctx.ensure(active=obj, mode="OBJECT", select=[obj])` for context-sensitive
  modifier/node operators.
- Use Blender as source of truth for modifier type support. Do not maintain another
  hardcoded type allowlist.

## File Map

- Modify: `src/niua_blender_mcp/domains/modifiers.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/modifiers.py`
- Modify: `tests/domains/test_modifiers.py`
- Add: `src/niua_blender_mcp/domains/geometry_nodes.py`
- Add: `blender_addon/niua_mcp_bridge/domains/geometry_nodes.py`
- Add: `tests/domains/test_geometry_nodes.py`
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

## Task 1: Modifier Types And Rich Stack Report

Interfaces:

- Change `modifiers.add.type` from enum to string.
- Add `modifiers.types`.
- Expand `modifiers.list` item fields:
  - `index`, `name`, `type`
  - `show_viewport`, `show_render`, `show_in_editmode`, `show_on_cage`, `show_expanded`
  - `is_active`, `execution_time`
  - `node_group`
  - shallow scalar `properties`

Steps:

1. Add fake-bpy tests:
   - router contains `modifiers.types`
   - `modifiers.add` accepts `TRIANGULATE`
   - `modifiers.types` returns fake enum identifiers/names
   - `modifiers.list` includes index/flags/node_group/properties
2. Run:
   - `pytest tests/domains/test_modifiers.py::test_router_contains_modifier_type_tool tests/domains/test_modifiers.py::test_add_accepts_live_modifier_type_not_static_allowlist tests/domains/test_modifiers.py::test_types_reports_live_modifier_enum tests/domains/test_modifiers.py::test_list_returns_rich_stack_report -v`
3. Implement server spec and add-on handler changes.
4. Run:
   - `pytest tests/domains/test_modifiers.py tests/test_parity.py -v`
5. Commit:
   - `git commit -m "feat: add live modifier type reporting"`

## Task 2: Visibility, Move, And Copy

Interfaces:

- Add `modifiers.set_visibility(object?, name, viewport?, render?, editmode?, cage?, expanded?)`
- Add `modifiers.move(object?, name, index)`
- Add `modifiers.copy(object?, name, new_name="")`

Steps:

1. Add fake-bpy tests:
   - visibility writes only provided flags and returns rich modifier report
   - move calls `object.modifier_move_to_index` in object mode and mutates stack order
   - copy calls `object.modifier_copy`, optionally renames copied modifier, and returns it
2. Run targeted red tests.
3. Implement server specs and add-on handlers.
4. Run:
   - `pytest tests/domains/test_modifiers.py tests/test_parity.py -v`
5. Commit:
   - `git commit -m "feat: add modifier stack controls"`

## Task 3: Geometry Nodes Create And Report

Interfaces:

- Add `geometry_nodes.create_modifier(object, name="")`
- Add `geometry_nodes.report(object, modifier="")`

Steps:

1. Add `tests/domains/test_geometry_nodes.py` fake-bpy coverage:
   - router contains both tool names
   - create uses `node.new_geometry_nodes_modifier` with object context
   - report returns modifier, group, interface sockets, nodes, and links
2. Run targeted red tests.
3. Add server specs in `src/niua_blender_mcp/domains/geometry_nodes.py`.
4. Add add-on handlers in `blender_addon/niua_mcp_bridge/domains/geometry_nodes.py`.
5. Run:
   - `pytest tests/domains/test_geometry_nodes.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add geometry nodes reports"`

## Task 4: Geometry Nodes Add And Link Nodes

Interfaces:

- Add `geometry_nodes.add_node(object, modifier="", type, name="")`
- Add `geometry_nodes.link(object, modifier="", from_node, from_socket, to_node, to_socket)`

Steps:

1. Extend fake-bpy geometry node tests:
   - add-node creates a node by `bl_idname` and optional name
   - link resolves node names and socket names or numeric indices
   - missing node/socket returns `invalid_params`
2. Run targeted red tests.
3. Implement specs and handlers.
4. Run:
   - `pytest tests/domains/test_geometry_nodes.py tests/test_parity.py -v`
5. Commit:
   - `git commit -m "feat: add geometry node graph editing"`

## Task 5: Live Smoke, Roadmap, Final Verification

Steps:

1. Add `test_modifiers_geometry_nodes_workflow` to `tests/test_smoke_headless.py`.
2. Update `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`:
   - subsystem 7 current/complete
   - next subsystem 8 Materials / Shading / Nodes / Textures
3. Run:
   - `pytest tests/test_smoke_headless.py::test_modifiers_geometry_nodes_workflow -v`
   - `pytest tests/test_smoke_headless.py -v`
   - `pytest`
   - `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'modifiers.types','modifiers.add','modifiers.list','modifiers.set_visibility','modifiers.move','modifiers.copy','geometry_nodes.create_modifier','geometry_nodes.report','geometry_nodes.add_node','geometry_nodes.link'}; print(required <= names)"`
   - `git status --short --branch`
4. Commit:
   - `git commit -m "test: cover modifiers geometry nodes workflow"`
