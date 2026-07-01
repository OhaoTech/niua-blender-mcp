# Senior rubric - game-ready organic prop

Score 0-10 on how a senior game artist would judge this prop from the supplied
multi-angle renders plus topology overlay. Be skeptical; default low when unsure.
Judge only what is visible in the supplied renders; if the topology overlay is
readable, score topology from it rather than defaulting low.

- **Silhouette and form flow (0-3):** Reads as a believable organic shape from all
  angles; bulges, asymmetry, and surface variation feel natural rather than
  randomly noisy; no pinching, lumps, or symmetry left over from the primitive.
- **Topology flow (0-3):** Edge loops follow the organic surface's curvature and
  support the silhouette; quads are evenly distributed; poles are placed in low-
  visibility areas (not on the silhouette or a highlight), not on flat or hard
  planes; no stray triangles/n-gons on visible curved surfaces.
- **Game-readiness (0-2):** Triangle count is appropriate for a prop; watertight;
  scale/orientation sane (Z-up, real-world-ish size).
- **Shading (0-2):** No visible shading errors, flipped normals, or faceting that
  smooth shading plus correct normals would fix; curved surfaces read smoothly.

## Score anchors

- **0-2:** Default primitive, broken mesh, or blockout with no meaningful craft.
- **3-4:** Primitive with minor edits; little design intent; topology may be clean
  but the result does not read as a finished organic prop.
- **5-6:** Clean, recognizable, simple organic form; acceptable but unremarkable,
  with limited silhouette/surface sophistication.
- **7-8:** Senior game-ready organic prop: purposeful surface flow, supporting
  loops, believable asymmetry and bulges, clean shading, and readable silhouette
  from several angles.
- **9-10:** Exceptional: production-polished form language, topology, silhouette,
  and shading with no visible weaknesses.

Return JSON: {"score": <0-10 float>, "critique": "<2-4 sentences, concrete>"}.
