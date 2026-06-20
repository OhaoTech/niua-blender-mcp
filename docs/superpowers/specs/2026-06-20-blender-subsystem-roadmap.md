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

Subsystem 3: Context / Selection / Modes.

Subsystem 1 is complete: app/session/file lifecycle tools are engine-neutral, and export
format is a parameter rather than a product-specific tool.

Subsystem 2 is complete as a data-backed `outliner.*` surface. It covers logical
scene tree reads, collection organization, object collection membership, parent
hierarchy, object/collection restriction flags, view layers, layer-collection
restrictions, and orphan listing/purge. GUI mouse/keyboard Outliner parity remains
deferred to subsystem 12.

Subsystem 3 is implemented as a `context.*` surface. It covers active object reads and
mutation, object selection actions, interaction mode switching, mesh select mode,
editor-area discovery, and operator poll checks in current or proposed context.

Next after verification: Subsystem 4, Object Creation / Transforms.
