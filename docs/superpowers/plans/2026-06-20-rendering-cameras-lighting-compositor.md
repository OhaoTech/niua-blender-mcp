# Implementation Plan: Subsystem 11 Rendering / Cameras / Lighting / Compositor

Date: 2026-06-20
Status: ready

## Global Constraints

- Follow TDD: write tests first, run targeted red, implement, run green, commit.
- Preserve `feedback.*` as the diagnostic visual-observation layer.
- Keep server specs and add-on commands in parity.
- Mutating scene/data tools must set `mutates=True`.
- `render.still` writes a file but restores prior scene render settings before returning.
- Compositor tools operate on `scene.node_tree` and follow existing node report/link shapes.

## File Map

- Create: `src/niua_blender_mcp/domains/rendering.py`
- Create: `blender_addon/niua_mcp_bridge/domains/rendering.py`
- Create: `tests/domains/test_rendering.py`
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

## Task 1: Cameras And Lights

Interfaces:

- `camera.create`, `camera.list`, `camera.report`, `camera.set`, `camera.set_active`
- `light.create`, `light.list`, `light.report`, `light.set`

Steps:

1. Create fake-bpy rendering tests with camera/light add operators and scene object data.
2. Add failing tests for router exposure, camera create/list/report/set/active, and light
   create/list/report/set.
3. Run targeted red tests.
4. Add server specs in `src/niua_blender_mcp/domains/rendering.py`.
5. Add add-on handlers in `blender_addon/niua_mcp_bridge/domains/rendering.py`.
6. Run:
   - `pytest tests/domains/test_rendering.py tests/test_parity.py -v`
7. Commit:
   - `git commit -m "feat: add camera and light controls"`

## Task 2: Render Settings, Still Render, And World

Interfaces:

- `render.settings`, `render.set_settings`, `render.still`
- `world.report`, `world.set`

Steps:

1. Extend fake-bpy rendering tests with render settings, world data, and a render operator
   that writes a fake PNG.
2. Add failing tests for render settings report/mutation, `render.still` file output and
   setting restoration, world report/set color and strength.
3. Run targeted red tests.
4. Add specs and handlers.
5. Run:
   - `pytest tests/domains/test_rendering.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add render and world controls"`

## Task 3: Compositor Node Tree

Interfaces:

- `compositor.enable`, `compositor.report`, `compositor.add_node`, `compositor.link`

Steps:

1. Extend fake-bpy rendering tests with scene compositor node trees, nodes, sockets, and
   links.
2. Add failing tests for enable/report/add-node/link and missing socket errors.
3. Run targeted red tests.
4. Add specs and handlers.
5. Run:
   - `pytest tests/domains/test_rendering.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add compositor node controls"`

## Task 4: Live Smoke, Roadmap, Final Verification

Steps:

1. Add `test_rendering_cameras_lighting_compositor_workflow` to `tests/test_smoke_headless.py`.
2. Update roadmap: subsystem 11 complete, next subsystem 12 UI Automation / GUI Parity Layer.
3. Run:
   - `pytest tests/test_smoke_headless.py::test_rendering_cameras_lighting_compositor_workflow -v`
   - `pytest tests/test_smoke_headless.py -v`
   - `pytest`
   - `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'camera.create','camera.list','camera.report','camera.set','camera.set_active','light.create','light.list','light.report','light.set','render.settings','render.set_settings','render.still','world.report','world.set','compositor.enable','compositor.report','compositor.add_node','compositor.link'}; print(required <= names); print(sorted(required - names))"`
   - `git status --short --branch`
4. Commit:
   - `git commit -m "test: cover rendering workflow"`
