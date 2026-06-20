# Playbook - clean game-ready topology

Goal: all-quad, even, deformation-friendly topology with a clean silhouette.

## Recipe

1. Block the form first; do not chase detail before proportions read from 4 angles.
2. Keep quads. Convert stray tris/n-gons: select all in Edit Mode, then
   `mesh.tris_convert_to_quads` or `model.retopo_quads`. Re-check `quad_ratio`.
3. Make normals consistent with `mesh.normals_make_consistent` and remove doubles
   with `mesh.remove_doubles` before judging. Flipped normals read as shading errors.
4. Place poles where the surface relaxes: corners and flat interiors, not curved
   silhouette edges or flat spans you want to stay flat.
5. Apply transforms before export; check `transform_applied`.

## Heuristics

- Even quad density beats raw quad count; long thin quads on curvature pinch shading.
- A pole on the silhouette is almost always wrong; move it inward.
- N-gons are acceptable only on flat, hidden, non-deforming faces. Prefer zero.
- If a loop does not follow the form, it is decoration; remove it.
