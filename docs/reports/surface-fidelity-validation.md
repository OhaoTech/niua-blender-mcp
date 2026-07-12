# Surface-fidelity metric — validation gate (Phase A)

**Date:** 2026-07-12 · **Gate:** the metric must be deterministic (self ≈ 1.0) AND flag the raw-decimate detail loss the silhouette metric misses, BEFORE any bake code (Phase B). **Verdict: PASS.**

## Test 1 — determinism / self-fidelity

An unchanged mesh compared against its own intake baseline:

| asset | silhouette IoU | surface_fidelity |
|---|---|---|
| real_creature (no edits) | 1.0 | **1.0** |

Self-fidelity is exactly 1.0 — the block-SSIM of a shaded render against itself, and the EEVEE fixed-frame render is deterministic enough that the two captures are identical. The metric does not drift.

## Test 2 — the metric catches the troll (the whole point)

The raw `make_game_ready` finisher (decimates to budget WITHOUT baking detail) was run on the dense assets, then both metrics read:

| asset | silhouette IoU (old, passed) | **surface_fidelity (new)** | floor 0.90 |
|---|---|---|---|
| real_prop (samurai, 978k tris) | 0.895 ✓ | **0.194** | ✗ far below |
| real_character | 0.926 ✓ | **0.319** | ✗ far below |
| real_creature | 0.987 ✓ | **0.237** | ✗ far below |

The silhouette metric passed all three (0.90–0.99) — this is the exact false-pass that let the faceted troll/samurai through. The surface-fidelity metric flags all three hard (0.19–0.32), far below the 0.90 floor. **The ruler now detects the detail destruction the silhouette was blind to.**

## Gate decision

**PASS.** Self-fidelity is 1.0 (deterministic); the metric flags the raw decimate well below floor on every dense asset where the silhouette wrongly passed. The floor of 0.90 is well-separated from both the good case (1.0) and the bad case (0.19–0.32) — no tuning needed. Phase B (the bake-transfer move + `bake_and_finish` skill, graded by this now-trusted metric) is cleared to proceed.

## Notes

- Determinism confirmed live; no denoise/AA-dither issues observed (self = exactly 1.0).
- The metric is measure-and-flag: unmeasured (headless/no-GL) → `available:false`, never a fake pass — consistent with the silhouette axis.
- Operational note: a stale Blender process from a prior session initially served pre-A4 code (surface_fidelity absent); a clean relaunch of the addon resolved it. Re-verified the running addon returns `surface_fidelity` before trusting these numbers.

## Floor recalibration (2026-07-12, Phase B live findings — supersedes the 0.90 above)
The 0.90 floor stated above was an unvalidated Phase-A guess. Phase B's live bake evidence showed the metric cleanly separates two populations: naive-decimate garbage 0.19-0.34, good high->low bakes 0.82-0.90. The floor was recalibrated to **0.60** (in the gap: still rejects the garbage this metric was built to catch, accepts a real bake). See docs/reports/bake-and-finish-first-run.md.
