# Altimeter — Baseline Reading

**Date:** 2026-07-01
**Run:** `workflows/altimeter.mjs` (workflow `wf_138a573d-8bf`), live visible Blender 5.1.2 on port 8765.
**Cost:** 44 agents, ~2.48M tokens, ~34 min.
**Pipeline under test:** Layer 2 as of branch `layer2-phase0-altimeter` (Waves 1–9B; Wave 10 not built).

## The number every later wave must beat

| Metric | Baseline |
|--------|----------|
| **Mean senior score** | **3.94 / 10** |
| **Senior pass rate** (gates pass AND judge ≥ 7.0) | **0 / 7 (0%)** |
| **Objective gate pass rate** | **7 / 7 (100%)** |
| **Weakest lens** | **silhouette** |

## Per-item

| Item | Class | Gates | Overall | sil | prop | topo | mat | design |
|------|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| from_scratch_barrel | from_scratch_prop | ✅ | **6.6** | 7.0 | 6.5 | 6.5 | 6.5 | 6.5 |
| generated_shell | generated_cleanup | ✅ | 5.8 | 5.5 | 5.5 | 6.5 | 5.0 | 6.5 |
| organic_pumpkin | organic_prop | ✅ | 5.1 | 5.0 | 5.0 | 5.5 | 5.5 | 4.5 |
| hard_surface_crate | hard_surface_prop | ✅ | 3.6 | 2.5 | 3.5 | 4.0 | 5.0 | 3.0 |
| organic_rock | organic_prop | ✅ | 2.9 | 2.5 | 2.5 | 3.0 | 3.0 | 3.5 |
| hard_surface_bracket | hard_surface_prop | ✅ | 2.0 | 2.0 | 2.0 | 2.5 | 1.5 | 2.0 |
| generated_blob | generated_cleanup | ✅ | 1.6 | 2.0 | 2.0 | 1.5 | 1.5 | 1.0 |

**Per-class mean:** from_scratch 6.6 · generated_cleanup 3.7 · organic 4.0 · hard_surface 2.8.

**Per-lens mean (weakest → strongest):** silhouette 3.79 · proportion 3.86 · design_intent 3.86 · material_read 4.00 · topology 4.21.

## What this proves

- **Gates are a real floor and completely insufficient.** Every item was driven to a fully
  gate-passing, LOD'd, collision-proxied, *exported* asset (verified live: bench objects show
  `stage: exported, complete: True` with `_LOD1`/`_COL` variants) — yet the judge panel, looking
  at real saved renders, scored them 1.6–6.6, mean 3.9, **zero senior passes.** The gap between
  100% gate-pass and 0% senior is exactly what the altimeter exists to measure.
- **The pipeline is strongest where it has gates+verbs (topology 4.21) and weakest at FORM
  (silhouette 3.79, proportion 3.86, design 3.86).** It cleans topology but does not craft
  believable form. This is the opposite of where effort has gone (most craft verbs are
  hard-surface/topology).
- **"Cleanup" is the hard problem.** The best item (barrel, 6.6) was built from a clean primitive;
  the worst (blob, 1.6) tried to rescue a noisy triangulated input — recovering valid topology
  does not recover coherent form. hard_surface scored *worst* by class (2.8) despite the most verbs.

## Implication for Phase 1 (reprioritized by data)

The finish-line roadmap assumed the quality ceiling was **real bake + real materials**. The
baseline says that lifts `material_read` (currently 4.0) but is **not** the biggest lever — the
three weakest lenses are all **form** (silhouette / proportion / design_intent, ~3.8). So Phase 1
should **lead with form-crafting capability** — blockout quality, proportion, silhouette-aware
modeling, and form recovery for messy inputs — *then* bake/materials. Retopo/topology is already
the pipeline's strength and needs the least new investment.

## Targets

- Near-term: `pass_rate > 0` (get at least one item to a genuine senior ≥ 7.0).
- Phase-1 exit: `mean_overall ≥ 5.5` and `silhouette` no longer the weakest lens.
- Definition-of-Done (roadmap §3): all held-out items senior on unseen inputs.

*Raw scorecards + saved renders: `/tmp/niua_altimeter/` (uncommitted). Rerun: launch visible
Blender on 8765, then `Workflow({ scriptPath: "workflows/altimeter.mjs", args: { port: 8765 } })`.*
