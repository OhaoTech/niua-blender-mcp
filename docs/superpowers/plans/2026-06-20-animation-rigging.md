# Implementation Plan: Subsystem 10 Animation / Rigging

Date: 2026-06-20
Status: ready

## Global Constraints

- Follow TDD: write tests first, run targeted red, implement, run green, commit.
- Preserve existing `anim.*` and `rig.*` behavior.
- Keep server specs and add-on commands in parity.
- Mutating tools must set `mutates=True`.
- Pose tools must use `ctx.ensure(active=armature, mode="POSE", select=[armature])`.
- Rest-bone tools continue using edit mode; object binding continues using object mode.
- Reflection remains the fallback for GUI/editor-specific operators.

## File Map

- Modify: `src/niua_blender_mcp/domains/animation.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/animation.py`
- Modify: `tests/domains/test_animation.py`
- Modify: `src/niua_blender_mcp/domains/rigging.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/rigging.py`
- Modify: `tests/domains/test_rigging.py`
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

## Task 1: Timeline And Detailed Keyframes

Interfaces:

- `anim.timeline()`
- `anim.set_timeline(frame_current?, frame_start?, frame_end?, fps?)`
- `anim.keyframes(object?)`

Steps:

1. Extend `tests/domains/test_animation.py` fake scene with frame start/end, preview
   range, and render FPS fields.
2. Add failing tests:
   - router contains the new tools
   - `anim.timeline` returns the current scene timeline
   - `anim.set_timeline` mutates only provided fields and pushes undo
   - `anim.keyframes` returns f-curve data paths, array indices, frames, values, and
     interpolation
3. Run targeted red tests:
   - `pytest tests/domains/test_animation.py::test_router_contains_animation_timeline_tools tests/domains/test_animation.py::test_timeline_reports_scene_range tests/domains/test_animation.py::test_set_timeline_updates_provided_fields tests/domains/test_animation.py::test_keyframes_reports_fcurve_points -v`
4. Add server specs in `src/niua_blender_mcp/domains/animation.py`.
5. Add add-on handlers in `blender_addon/niua_mcp_bridge/domains/animation.py`.
6. Run:
   - `pytest tests/domains/test_animation.py tests/test_parity.py -v`
7. Commit:
   - `git commit -m "feat: add animation timeline reports"`

## Task 2: Pose Reports And Pose Transforms

Interfaces:

- `rig.report(armature)`
- `rig.pose_report(armature, bone?)`
- `rig.set_pose_bone(armature, bone, location?, rotation?, scale?, rotation_mode="XYZ")`
- `rig.clear_pose(armature)`

Steps:

1. Extend `tests/domains/test_rigging.py` fake armature objects with `pose.bones`, pose
   bone transforms, and constraint lists.
2. Add failing tests:
   - router contains pose tools
   - `rig.pose_report` reports all pose bones and one named pose bone
   - `rig.set_pose_bone` enters POSE mode and updates only provided transform fields
   - `rig.clear_pose` resets all pose transforms
   - `rig.report` includes rest bones, pose bones, constraints, and child meshes
3. Run targeted red tests.
4. Add server specs in `src/niua_blender_mcp/domains/rigging.py`.
5. Add add-on handlers in `blender_addon/niua_mcp_bridge/domains/rigging.py`.
6. Run:
   - `pytest tests/domains/test_rigging.py tests/test_parity.py -v`
7. Commit:
   - `git commit -m "feat: add rig pose controls"`

## Task 3: Pose Constraints

Interfaces:

- `rig.constraints(armature, bone?)`
- `rig.constraint_add(armature, bone, type, name?, target?, subtarget?, influence=1.0)`
- `rig.constraint_remove(armature, bone, name)`

Steps:

1. Extend fake pose-bone constraints with `new(type)`, `get(name)`, and `remove`.
2. Add failing tests:
   - `rig.constraints` reports all constraints or one bone's constraints
   - `rig.constraint_add` sets type, name, influence, target, and subtarget
   - `rig.constraint_remove` removes by name
   - unsupported constraint type raises `invalid_params`
3. Run targeted red tests.
4. Add server specs and add-on handlers.
5. Run:
   - `pytest tests/domains/test_rigging.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add rig constraint controls"`

## Task 4: Vertex Groups And Skinning Weights

Interfaces:

- `rig.vertex_groups(mesh)`
- `rig.vertex_group_create(mesh, name)`
- `rig.assign_weights(mesh, group, vertices, weight=1.0, mode=REPLACE|ADD|SUBTRACT)`

Steps:

1. Extend fake mesh data with vertices, vertex group collections, and vertex weight
   assignments.
2. Add failing tests:
   - `rig.vertex_groups` lists groups and assigned vertex weights
   - `rig.vertex_group_create` creates a named group and returns the report
   - `rig.assign_weights` parses comma-separated indices and calls `group.add`
   - invalid vertex indices raise `invalid_params`
3. Run targeted red tests.
4. Add server specs and add-on handlers.
5. Run:
   - `pytest tests/domains/test_rigging.py tests/test_parity.py -v`
6. Commit:
   - `git commit -m "feat: add rig vertex weight controls"`

## Task 5: Live Smoke, Roadmap, Final Verification

Steps:

1. Replace the existing narrow animation/rigging smokes with `test_animation_rigging_workflow`.
2. Update roadmap: subsystem 10 complete, next subsystem 11 Rendering / Cameras /
   Lighting / Compositor.
3. Run:
   - `pytest tests/test_smoke_headless.py::test_animation_rigging_workflow -v`
   - `pytest tests/test_smoke_headless.py -v`
   - `pytest`
   - `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; required={'anim.timeline','anim.set_timeline','anim.keyframes','rig.report','rig.pose_report','rig.set_pose_bone','rig.clear_pose','rig.constraints','rig.constraint_add','rig.constraint_remove','rig.vertex_groups','rig.vertex_group_create','rig.assign_weights'}; print(required <= names); print(sorted(required - names))"`
   - `git status --short --branch`
4. Commit:
   - `git commit -m "test: cover animation rigging workflow"`
