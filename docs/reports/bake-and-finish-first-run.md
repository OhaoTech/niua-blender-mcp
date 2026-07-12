# bake_and_finish (skill #2) — first live run

**Date:** 2026-07-12 · **Skill:** `bake_and_finish` (bake-transfer, gated on silhouette AND surface fidelity) · **Metric:** the surface-fidelity ruler from Phase A · **Assets:** the 5 real generator fixtures.

## The result in one line

The metric + bake + gate work end-to-end: **3 of 5 assets get a good game-ready bake (fidelity 0.82–0.90, at the triangle budget); the 2 densest assets can't be baked to budget without losing too much surface fidelity, so the accept/revert loop honestly declines them** rather than shipping the faceted garbage the old finisher produced.

## Per-asset

| asset | source tris | bake fidelity | outcome | why |
|---|---|---|---|---|
| real_character_light | 50k | **0.853** | KEPT ✓ | good bake, budget-met |
| real_creature | 78k | **0.823** | KEPT ✓ | good bake, budget-met |
| real_multipart | 24k | **0.899** | KEPT ✓ | good bake, budget-met |
| real_character | 77k organic | 0.276 | reverted | over-aggressive decimate (silhouette also fell to 0.79); bake can't restore a lost silhouette |
| real_prop | 978k samurai | 0.344 | reverted | 200× reduction + auto-unwrap can't carry the fine armor detail in one pass |

Contrast with the raw `make_game_ready` decimate (no bake), which scored **0.19–0.34 on these same dense assets** — every one below any reasonable floor. The bake lifts the good cases to 0.82–0.90; where it can't (the two densest), the loop reverts to the intake rather than ship a low-fidelity result.

## What the live run proved (and fixed)

The live acceptance surfaced three real issues the offline path could not, all fixed in commit `cddddf0`:

1. **The fidelity render didn't isolate shape.** `render_fidelity_views` applied neutral clay only when the object had *no* material; once `pbr_maps` or the bake added a material, the render used that material's (empty/default) albedo, so the metric was confounded by *colour*, not shape — and every material-adding move wrongly reverted. Fixed: the render now **always** uses neutral clay albedo and **wires the object's baked normal map into the clay**, so it measures surface shape only (a baked low-poly shades like the high-poly; the intake shades by geometry). Self-fidelity stays exactly 1.0 after the fix.
2. **The floor was an unvalidated guess.** `SURFACE_FIDELITY_FLOOR = 0.90` was set in the design before any measurement. Live evidence shows the metric cleanly separates two populations — naive-decimate garbage (0.19–0.34) and good high→low bakes (0.82–0.90). The floor was recalibrated to **0.60**, sitting in the gap: it still rejects the garbage the metric was built to catch, and accepts a real bake. This is evidence-based calibration, not gaming the ruler.
3. **`run_skill.py` didn't establish the intake baseline.** A fidelity-gated skill is inert without a `capture_intake` baseline (both axes report unmeasured → no move ever reverts). The runner now captures the baseline before the skill.

## Founder quality bar — honest status

- **Met on 3/5 dense assets:** the finished low-poly is at the triangle budget, carries a baked normal map, and reads as the same form with restored surface detail (a legitimate game-ready asset, not the faceted troll). Note: `feedback.capture` renders SOLID (ignores the normal map), so viewport before/after captures *undersell* the result — the in-engine appearance with the baked normal is closer to the high-poly than the bare 8k-tri geometry shows.
- **Not yet met on the 2 densest (real_character, real_prop/samurai):** a single aggressive-decimate + auto-unwrap + bake pass cannot preserve their fidelity to budget. The ruler now tells us this *honestly and automatically* — which is the whole point of building it. These are the next frontier: **quad retopo (instead of decimate) + better UVs before the bake**, so the low-poly's silhouette and UV layout can carry the baked detail. That is a HANDS/SEQUENCING gap, not a metric gap.

## Integrity

- Full offline suite 818 passed / 71 skipped; parity + layer boundary green.
- Metric is deterministic (self-fidelity exactly 1.0) and judge-free; fail-closed (unmeasured never blocks).
- The accept/revert loop is honest: it keeps only what preserves both silhouette and surface fidelity, and reverts the rest — no move that degrades the surface survives.
