# Game-ready sports coupe — design

## Goal

Create a branded-neutral, all-angle PC vehicle asset in Blender whose silhouette and styling follow the supplied red exotic-coupe reference. The asset should be practical for Godot import, rather than a single-camera replica or an exact recreation of any real vehicle.

## Deliverable

- One isolated Blender scene containing the complete vehicle, studio lighting, and a reference-matched preview camera.
- A clean vehicle hierarchy with separately named body, glazing, lights, wheel assemblies, interior, trim, and collision objects.
- PBR materials: red clear-coat paint, smoked glass, dark rubber, machined alloy, black trim, light emitters, and simple interior surfaces.
- Export-ready GLB plus LOD0, LOD1, LOD2, and a separate low-poly collision proxy.

## Geometry and LODs

LOD0 is a roughly 45,000-triangle hero asset, with the budget concentrated in the body curvature and wheel faces. It includes a readable, simplified cabin but does not model hidden engine or mechanical detail.

LOD1 targets roughly 20,000 triangles by simplifying wheel spokes, cabin, lights, and minor body detail. LOD2 targets roughly 7,000 triangles with merged wheel detail and simplified opening geometry. The collision proxy is a small set of convex body and wheel volumes, independent of render meshes.

The body is a symmetric, clean quad-oriented approximation: wide front arches, low nose, swept canopy, pronounced rear haunches, and an integrated rear deck. Panel gaps, badges, exact manufacturer-specific lamp internals, and logo marks are excluded.

## Modeling and materials

The wheel/tire/brake set is modular and instanced across the vehicle, with left/right rotation handled by transforms. Headlamps and taillamps are independent meshes with emissive elements. Glass is separate from paint surfaces. Mirrors, door seams, intakes, diffuser, and side skirts are modeled only to the depth needed for close PC gameplay viewing.

All render meshes use applied transforms, outward normals, smooth shading with controlled sharp edges, and non-overlapping UVs. Materials use standard metallic/roughness PBR values and packed texture slots suitable for Godot.

## Camera and presentation

The scene includes a front three-quarter camera matching the supplied reference: low eye level, moderate focal length, neutral gray sweep, and soft studio key/fill/rim lighting. This camera proves the visual match but does not constrain the asset’s all-angle construction.

## Validation and export

Before handoff, validate that the scene has no missing material links, loose duplicate geometry, unapplied transforms, inverted normals, or objects outside the intended hierarchy. Confirm each LOD budget, collision separation, and a clean GLB export/import in Godot-compatible conventions (Y-up export, meters, named materials and nodes).

## Out of scope

- Exact replication of a manufacturer model, logos, or badging.
- Fully functional doors, suspension, steering, animations, rigging, or an engine bay.
- Photoreal scanned textures or a detailed underside.
