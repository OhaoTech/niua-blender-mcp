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

## Recipe - hard-surface crate

Use this ordered pass for the `modeling_prop` crate brief.

1. Start from a clean cube named for the subject. Keep real-world proportions close
   to a 1m box; do not stretch it into a plank or pillar.
2. Build readable design intent before small cleanup: a crate needs recessed side
   panels and softened outer edges, not just a subdivided cube.
3. Call `model.recess_panels` with an inset around `0.06-0.10` and depth around
   `0.025-0.05`. This creates the panel break and a clear mid-size form cue.
4. Call `model.bevel_edges` with angle around `30`, width around `0.015-0.035`,
   and `segments=2`. Bevels should catch highlights but not erase the box shape.
5. Call `model.retopo_quads` after paneling/beveling. Re-check that n-gons are zero
   and the quad ratio is still at least `0.95`.
6. If the silhouette looks too primitive, add purposeful supporting loops or shallow
   insets. Do not add random cuts; every loop should support a panel, bevel, or edge.
7. Use `mesh.shade_smooth` only after topology is clean. Smooth shading cannot hide
   bad loops, stretched quads, or poles on visible edges.
8. Verify with `feedback.quality`: `quad_ratio >= 0.95`, `ngons == 0`,
   `non_manifold_edges == 0`, and a sane triangle count.
9. Verify visually with `feedback.topology`: quads should dominate, wire edges should
   reveal even density, and defects should not sit on the silhouette.

## What pushes a prop from 5 to 8

- Purposeful edge flow: loops follow panel borders, bevel supports, and silhouette.
- Supporting loops are close enough to hold bevels but not so dense that the mesh
  looks noisy.
- Quad density is even across flat spans; long thin quads on bevel transitions cause
  visible shading problems.
- Poles belong on flat interiors or relaxed corners, not on curved silhouettes.
- The model reads as a crate from four angles before material work starts.
- Clean topology and readable shape matter more than raw face count.

## Heuristics

- Even quad density beats raw quad count; long thin quads on curvature pinch shading.
- A pole on the silhouette is almost always wrong; move it inward.
- N-gons are acceptable only on flat, hidden, non-deforming faces. Prefer zero.
- If a loop does not follow the form, it is decoration; remove it.
