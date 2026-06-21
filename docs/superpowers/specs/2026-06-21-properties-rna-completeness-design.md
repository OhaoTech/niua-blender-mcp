# Subsystem 13 Design: Properties Editor / RNA Completeness

Date: 2026-06-21
Status: implemented

## Goal

Close the gap between curated MCP tools and Blender's Properties editor data model.
The agent must be able to inspect and mutate object and mesh properties without
guessing which panel owns a field.

The design is reflection-first: Blender's live RNA metadata is the source of truth.
Curated domains stay useful for common workflows, but `properties.*` is the fallback
that prevents missing individual Object or Mesh Data Properties fields.

## Source Baseline

Blender source was pulled as an external reference at:

`/home/frankyin/Desktop/lab/blender-source`

Reference commit:

`1ef54e50 2026-06-21 Merge branch 'blender-v5.2-release'`

Source-backed UI shape:

- 21 editor spaces under `source/blender/editors/space_*`
- 20 Properties editor contexts from `SpaceProperties`
- 46 `scripts/startup/bl_ui/properties_*.py` files
- 17 object-data property panel files

The 20 Properties contexts are: Tool, Scene, Render, Output, View Layer, World,
Collection, Object, Constraint, Modifier, Data, Bone, Bone Constraint, Material,
Texture, Particles, Physics, Shader Effects, Strip, and Strip Modifier.

## API

`properties.report(path, include_values=True)`

Reports every live RNA property on a stable path target. Supported roots:

- `object:<object-name>`
- `data:<bpy.data collection>/<datablock-name>`

Examples:

- `object:Cube`
- `object:Cube/location`
- `object:Cube/data`
- `data:meshes/Cube`
- `data:scenes/Scene/render`

Path segments are slash-separated. Object/datablock names and custom-property keys
are percent-encoded when they contain `/` or other separators.

`properties.object_report(object, include_data=True, include_modifiers=True, include_values=True)`

Reports an object, its `object.data`, modifiers, and custom ID properties. This is the
Object Properties + Mesh Data Properties vertical slice.

`properties.get(path)`

Reads a stable path.

`properties.set(path, value)`

Sets a mutable RNA property or ID custom property. `value` is JSON-encoded.

`properties.unset(path)`

Deletes an ID custom property or resets an RNA property when Blender exposes
`property_unset`.

## Guarantees

- No hard-coded Object or Mesh property allowlist.
- Every property in `target.bl_rna.properties` except `rna_type` is represented in
  the report.
- Reports include metadata: identifier, label, description, RNA type, subtype,
  readonly state, array state, array length, enum items, stable path, readability,
  and current value when readable.
- Custom ID properties are first-class paths under `idprops`.
- Names containing dots or slashes are addressable through percent-encoded stable
  paths.
- Mutations flow through the normal command registry and push one undo step on
  success.

## Current Boundary

This subsystem closes object/mesh Properties data access. It does not by itself
implement every Properties editor context as a curated domain. The next GUI-parity
wave should use `properties.report/get/set` as the safety net while adding curated
surfaces for Tool settings, constraints, particles, physics, shader effects, sequencer
strips, and the remaining object-data types.
