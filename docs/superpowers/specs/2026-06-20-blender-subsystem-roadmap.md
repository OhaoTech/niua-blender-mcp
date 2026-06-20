# Blender MCP Subsystem Roadmap

Status: active roadmap.

Rule: implement subsystems in order. Do not advance to the next subsystem until
the current subsystem has explicit read tools, mutation tools, reflection or
operator fallback where appropriate, fake-bpy tests, real-Blender smoke coverage
for high-risk behavior, and documented gaps.

## Subsystems

1. App / Session / Files
2. Scene Tree / Outliner
3. Context / Selection / Modes
4. Object Creation / Transforms
5. Mesh Modeling
6. Curves / Text / Grease Pencil / Non-Mesh Geometry
7. Modifiers / Geometry Nodes
8. Materials / Shading / Nodes / Textures
9. UV / Images
10. Animation / Rigging
11. Rendering / Cameras / Lighting / Compositor
12. UI Automation / GUI Parity Layer

## Coverage Matrix

For each subsystem, track:

- Read state: inspect what Blender shows.
- Mutate state: perform stable API/operator changes.
- Invoke ops: expose operator-backed actions safely.
- Visual feedback: capture/render relevant views.
- GUI parity: document whether GUI-only interaction remains.
- Tests: fake-bpy unit tests plus live Blender smoke where behavior depends on Blender.

## Current Focus

Subsystem 12: UI Automation / GUI Parity Layer.

Subsystem 1 is complete: app/session/file lifecycle tools are engine-neutral, and export
format is a parameter rather than a product-specific tool.

Subsystem 2 is complete as a data-backed `outliner.*` surface. It covers logical
scene tree reads, collection organization, object collection membership, parent
hierarchy, object/collection restriction flags, view layers, layer-collection
restrictions, and orphan listing/purge. GUI mouse/keyboard Outliner parity remains
deferred to subsystem 12.

Subsystem 3 is complete as a `context.*` surface. It covers active object reads and
mutation, object selection actions, interaction mode switching, mesh select mode,
editor-area discovery, and operator poll checks in current or proposed context.

Subsystem 4 is implemented as an `object.*` surface. It covers common primitive and
empty creation, object duplication, object deletion, renaming, transform reads and
mutation, transform application, origin setting, and local/world bounds reads. It keeps
specialized object families such as cameras, lights, curves, text, armatures, and GUI
mouse/keyboard parity deferred to their later subsystems.

Subsystem 5 is implemented as an expanded `mesh.*` surface. It covers explicit mesh
selection reports, select-all, index-based vertex/edge/face selection, delete, dissolve,
merge, remove doubles, tri/quad conversion, fill, edge/face creation, the previous
extrude/bevel/inset/subdivide/normal/shading tools, and analytic topology reporting.
Viewport mouse picking, knife drawing, box/lasso selection, gizmos, and other event-led
mesh workflows remain deferred to subsystem 12.

Subsystem 6 is implemented as a `geometry.*` surface. It covers curve, text, surface,
metaball, and grease pencil object creation; non-mesh geometry reporting; curve-like
data setters; text setters; and conversion to mesh through Blender's object conversion
operator. Fine-grained curve point editing, text cursor editing, grease pencil stroke
authoring, and GUI event parity remain deferred to later focused work and subsystem 12.

Subsystem 7 is implemented as `modifiers.*` plus `geometry_nodes.*`. It covers live
modifier type discovery, unrestricted modifier creation through Blender's own type
validation, rich stack reports, common visibility flags, stack move/copy/apply/remove,
default Geometry Nodes modifier creation, node group reporting, generic node creation,
and socket linking. GUI node editor gestures and advanced node group interface/bake
panels remain deferred to subsystem 12 and later focused Geometry Nodes work.

Subsystem 8 is implemented as expanded `shading.*` plus `textures.*`. It covers
material creation/assignment, Principled BSDF editing, material and shader node-tree
reporting, generic shader node creation, shader socket linking, node input default
editing from JSON, image texture wiring, image datablock load/list/report, and live
smoke coverage for shader graph plus texture wiring. UV layout/editing, texture
painting, and baking remain deferred to subsystem 9 and later Layer 2 work.

Subsystem 9 is implemented as expanded `uv.*` plus the image datablock tools from
subsystem 8. It covers UV layer listing/creation/activation/deletion, seam reports
and mutation, unwrap/projection/pack/average-scale operators, analytic UV reports,
and UV layout image export. Texture painting, baking, UDIM/tile-specific editing,
and GUI event parity remain deferred to later focused work and subsystem 12.

Subsystem 10 is implemented as expanded `anim.*` plus expanded `rig.*`. It covers
timeline range/current-frame/FPS reads and mutation, detailed action/f-curve/keyframe
reports, existing keyframe insertion/deletion/interpolation, armature rest-bone
authoring, pose bone reports and transforms, pose constraint list/add/remove, vertex
group reports/creation, and deterministic skinning weight assignment by vertex index.
Graph Editor, Dope Sheet, NLA, driver editing, weight-paint brush gestures, and control
rig recipe workflows remain available through reflection or deferred to subsystem 12 and
Layer 2.

Subsystem 11 is implemented as `camera.*`, `light.*`, `render.*`, `world.*`, and
`compositor.*`. It covers camera creation/list/report/edit/activation, light
creation/list/report/edit, render settings report/mutation, headless Workbench still
rendering to disk with settings restoration, world color/background strength, and
compositor node-tree enable/report/add/link. Viewport camera/light gizmos, render-region
dragging, compositor editor gestures, and production lighting/render artistry remain
deferred to subsystem 12 and Layer 2.

Next: implement Subsystem 12, UI Automation / GUI Parity Layer.
