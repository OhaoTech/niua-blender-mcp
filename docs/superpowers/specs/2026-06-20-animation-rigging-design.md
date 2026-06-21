# Subsystem 10 Design: Animation / Rigging

Date: 2026-06-20
Status: implemented

## Goal

Make Blender's animation and rigging data controllable without the Timeline, Dope Sheet,
Graph Editor, Armature, Pose, or Weight Paint GUIs:

- inspect and set timeline range, current frame, and frame rate
- inspect object actions, f-curves, and individual keyframes
- insert/delete keyframes and set interpolation through existing tools
- create armatures and edit rest bones through existing tools
- inspect and edit pose bone transforms
- inspect, add, and remove pose bone constraints
- inspect/create vertex groups and assign skinning weights by vertex index

The generated capability surface remains the floor for every Blender operator:
`capabilities.search`, `capabilities.describe`, and `capabilities.invoke` expose the
long tail of Graph Editor, Dope Sheet, NLA, pose, armature, and constraint operators.
This subsystem adds the durable data APIs an agent needs before it invokes those
operators.

## What We Have

Existing curated animation tools:

- `anim.set_frame(frame)`
- `anim.insert_keyframe(object?, data_path, frame?, index=-1)`
- `anim.delete_keyframe(object?, data_path, frame?, index=-1)`
- `anim.set_interpolation(object?, interpolation=CONSTANT|LINEAR|BEZIER)`
- `anim.list_actions()`
- `anim.report(object?)`

Existing curated rigging tools:

- `rig.add_armature(name?, location?)`
- `rig.add_bone(armature, name, head?, tail?)`
- `rig.set_bone_transform(armature, bone, head?, tail?)`
- `rig.parent_with_auto_weights(mesh, armature)`
- `rig.list_bones(armature)`

Current strengths:

- Keyframing uses datablock methods, not GUI operators.
- F-curve discovery already supports Blender 5.x slotted/layered actions.
- Armature rest-bone editing runs in edit mode through `ctx.ensure`.
- Live smoke covers basic keyframes and edit-bone persistence.

Current gaps:

- No timeline/range/fps report or range mutation.
- `anim.report` gives counts, not the actual f-curves and keyframe coordinates.
- No pose-bone read or transform tools.
- No curated pose constraint tools.
- No vertex group/weight read or assignment tools.
- No single rig report that ties rest bones, pose bones, constraints, and skinning state
  together.

## Capability Surface

### Animation

`anim.timeline()`

Read-only. Returns scene name, `frame_current`, `frame_start`, `frame_end`,
`use_preview_range`, preview start/end, `fps`, and `fps_base`.

`anim.set_timeline(frame_current?, frame_start?, frame_end?, fps?)`

Sets only provided scene timeline fields. Uses `scene.frame_set(frame_current)` for the
playhead and direct scene/render properties for range and FPS. Returns `anim.timeline`.

`anim.keyframes(object?)`

Read-only. Returns action name, frame range, total f-curve/keyframe counts, and each
f-curve with `data_path`, `array_index`, and keyframe points as `{frame, value,
interpolation}`.

Existing keyframe insert/delete/interpolation tools remain unchanged.

### Rigging And Posing

`rig.report(armature)`

Read-only. Returns rest bones, pose bones, pose constraints, and child mesh names whose
parent is the armature.

`rig.pose_report(armature, bone?)`

Read-only. Returns pose bone transforms and constraints. If `bone` is omitted, reports
all pose bones.

`rig.set_pose_bone(armature, bone, location?, rotation?, scale?, rotation_mode="XYZ")`

Runs in POSE mode. Sets only provided transform fields on `armature.pose.bones[bone]`.
`rotation` is Euler radians using `rotation_mode`.

`rig.clear_pose(armature)`

Runs in POSE mode. Clears all pose bone location, rotation, and scale to rest values.
Returns the pose report.

### Pose Constraints

`rig.constraints(armature, bone?)`

Read-only. Lists pose bone constraints. If `bone` is omitted, reports every pose bone.

`rig.constraint_add(armature, bone, type, name?, target?, subtarget?, influence=1.0)`

Creates a pose bone constraint with Blender's live `constraints.new(type=<type>)`.
Optional `target` resolves any object by name; `subtarget` is written when Blender exposes
it.

`rig.constraint_remove(armature, bone, name)`

Removes a named pose bone constraint and returns the updated constraint report.

### Skinning Weights

`rig.vertex_groups(mesh)`

Read-only. Lists vertex groups and assigned vertex weights.

`rig.vertex_group_create(mesh, name)`

Creates a vertex group and returns the updated vertex group report.

`rig.assign_weights(mesh, group, vertices, weight=1.0, mode=REPLACE|ADD|SUBTRACT)`

Assigns a comma-separated list of vertex indices to a named vertex group through
`vertex_group.add(indices, weight, mode)`. Returns the updated vertex group report.

Existing `rig.parent_with_auto_weights` remains the automatic skin-binding path.

## Error Handling

- Missing objects return `not_found`.
- Wrong object type, missing active object, missing data path, or missing scene return
  `precondition_failed`.
- Missing bones, constraints, or vertex groups return `not_found`.
- Bad vertex index strings, out-of-range vertices, and unsupported assignment modes return
  `invalid_params`.
- Unsupported constraint types return `invalid_params`.
- Operator poll failures return `precondition_failed`.

## Testing

Fake-bpy tests cover:

- server/add-on parity for every new tool
- timeline read/mutation
- f-curve/keyframe detailed report
- rig report and pose report
- pose bone transform set and clear
- constraint add/list/remove, including target/subtarget
- vertex group create/report/assign, including invalid vertex indices

Real Blender smoke covers:

1. create an animated cube, set timeline range/fps, insert keyframes, inspect f-curves
2. create an armature with two bones, set a pose transform, add/remove a constraint
3. create a mesh, create a vertex group, assign weights, bind to the armature
4. assert reports show the expected pose, constraint, and skinning state

## Deferred

- GUI editor gestures: Timeline/Dope Sheet/Graph/NLA box select, dragging handles, marker
  manipulation, channel row clicks, and keyframe mouse editing stay in subsystem 12.
- High-level walk cycles, retargeting, control-rig generation, IK/FK rig recipes, and
  animation cleanup judgment belong to Layer 2 craft verbs.
- Detailed driver authoring and NLA strip composition remain accessible through RNA and
  generated operator reflection for now; a future focused pass can add curated tools if
  agent workflows need them frequently.
