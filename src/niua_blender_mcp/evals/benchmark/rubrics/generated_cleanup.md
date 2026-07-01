# Senior rubric - cleaned-up generated/scanned prop

Score 0-10 on how a senior game artist would judge this prop from the supplied
multi-angle renders plus topology overlay. Be skeptical; default low when unsure.
Judge only what is visible in the supplied renders; if the topology overlay is
readable, score topology from it rather than defaulting low.

- **Topology recovery (0-3):** The noisy/triangulated/scan-like starting mesh has
  been rebuilt into deliberate quad flow; no leftover triangulation artifacts,
  uneven density, or scan noise remains visible; edge loops follow the recovered
  form rather than the original raw geometry.
- **Watertightness and manifold health (0-3):** No loose vertices, non-manifold
  edges, holes, or duplicate geometry remain from the generated source; the mesh
  is a single clean, closed (or intentionally open with clean boundaries) surface.
- **Game-readiness (0-2):** Triangle count is appropriate for a prop; scale/
  orientation sane (Z-up, real-world-ish size).
- **Shading (0-2):** No visible shading errors, flipped normals, or faceting that
  smooth shading plus correct normals would fix.

## Score anchors

- **0-2:** Raw generated/triangulated mesh untouched, or still broken/non-manifold
  with no meaningful cleanup.
- **3-4:** Some cleanup attempted; scan noise or triangulation artifacts still
  visible; topology may be clean in patches but the result does not read as a
  finished prop.
- **5-6:** Clean, recognizable, simple recovered form; acceptable but unremarkable,
  with limited topology sophistication.
- **7-8:** Senior game-ready cleanup: purposeful edge flow recovered from the
  generated source, watertight, clean shading, and readable proportions from
  several angles.
- **9-10:** Exceptional: production-polished form language, topology, and shading
  with no visible weaknesses or trace of the original generated artifacts.

Return JSON: {"score": <0-10 float>, "critique": "<2-4 sentences, concrete>"}.
