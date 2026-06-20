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

Subsystem 1: App / Session / Files.

The file/export surface must be engine-neutral. Blender MCP tools should not encode
consumer names such as game engines or orchestrators. Export format is a parameter,
not a separate product-specific tool.
