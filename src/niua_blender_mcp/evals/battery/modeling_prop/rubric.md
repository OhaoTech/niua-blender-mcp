# Senior rubric - game-ready hard-surface prop

Score 0-10 on how a senior game artist would judge this prop from the supplied
multi-angle renders plus topology overlay. Be skeptical; default low when unsure.

- **Topology flow (0-3):** Edge loops follow form; quads are evenly distributed;
  poles are placed where they relax, not on flat spans or silhouette edges; no
  triangles/n-gons on deforming or highlight areas.
- **Silhouette and proportion (0-3):** Reads cleanly from all angles; proportions
  are believable; no lumps, pinching, or asymmetry that should be symmetric.
- **Game-readiness (0-2):** Triangle count is appropriate for a prop; watertight;
  scale/orientation sane (Z-up, real-world-ish size).
- **Shading (0-2):** No visible shading errors, flipped normals, or faceting that
  smooth shading plus correct normals would fix.

Return JSON: {"score": <0-10 float>, "critique": "<2-4 sentences, concrete>"}.
