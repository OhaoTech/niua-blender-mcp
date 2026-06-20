# Implementation Plan: Subsystem 8 Materials / Shading / Nodes / Textures

Date: 2026-06-20
Status: ready

## Global Constraints

- Follow TDD: tests first, targeted red command, implementation, green command, commit.
- Keep server specs and add-on commands in parity.
- Mutating tools must set `mutates=True`.
- Shader node link handlers must use Blender's live `node_tree.links.new(input, output)`
  order.
- UV unwrap, UV editing, baking, and image painting stay out of this subsystem.

## File Map

- Modify: `src/niua_blender_mcp/domains/shading.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/shading.py`
- Modify: `tests/domains/test_shading.py`
- Add: `src/niua_blender_mcp/domains/textures.py`
- Add: `blender_addon/niua_mcp_bridge/domains/textures.py`
- Add: `tests/domains/test_textures.py`
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

## Task 1: Material And Shader Node Report

Interfaces:

- Add `shading.report(material="", object="")`.

Steps:

1. Extend fake-bpy shading tests:
   - router contains `shading.report`
   - reports material name, use_nodes, nodes, inputs, outputs, links
   - object mode includes material slot list and active slot
2. Run targeted red tests.
3. Add server spec.
4. Add add-on report handler.
5. Run:
   - `pytest tests/domains/test_shading.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add shading material reports"`

## Task 2: Generic Shader Node Editing

Interfaces:

- Add `shading.add_node(material, type, name="")`.
- Add `shading.link_nodes(material, from_node, from_socket, to_node, to_socket)`.
- Add `shading.set_node_input(material, node, input, value)`.

Steps:

1. Extend fake-bpy shading tests:
   - add-node creates a node by `bl_idname` and optional name
   - link resolves node/socket names and returns a link report
   - set-node-input parses JSON number and vector values
   - missing node/socket returns `invalid_params`
2. Run targeted red tests.
3. Add server specs.
4. Add add-on handlers and shared node/socket report helpers.
5. Run:
   - `pytest tests/domains/test_shading.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add shader node editing"`

## Task 3: Texture/Image Datablock Tools

Interfaces:

- Add `textures.load(path, name="")`.
- Add `textures.list()`.
- Add `textures.report(name)`.

Steps:

1. Add `tests/domains/test_textures.py` with fake image datablocks:
   - router contains all three tools
   - load calls `bpy.data.images.load`, optional rename
   - list/report return name, filepath, size, source, colorspace
   - missing image returns `not_found`
2. Run targeted red tests.
3. Add server specs and add-on handlers.
4. Run:
   - `pytest tests/domains/test_textures.py tests/test_parity.py -v`
5. Commit:
   - `git commit -m "feat: add texture image datablock tools"`

## Task 4: Live Smoke, Roadmap, Final Verification

Steps:

1. Add `test_materials_shading_textures_workflow` to `tests/test_smoke_headless.py`.
2. Update `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`:
   - subsystem 8 current/complete
   - next subsystem 9 UV / Images
3. Run:
   - `pytest tests/test_smoke_headless.py::test_materials_shading_textures_workflow -v`
   - `pytest tests/test_smoke_headless.py -v`
   - `pytest`
   - `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'shading.report','shading.add_node','shading.link_nodes','shading.set_node_input','textures.load','textures.list','textures.report'}; print(required <= names)"`
   - `git status --short --branch`
4. Commit:
   - `git commit -m "test: cover materials shading textures workflow"`
