# Design — Eval Redesign: Readiness + Do-No-Harm Preservation

**Date:** 2026-07-02
**Status:** Design (for review) — supersedes the absolute-form altimeter judge for grading THIS tool.
**Depends on:** the form-rethink (`2026-07-02-form-rethink.md`) — this tool is a technical FINISHER that
preserves inherited form, graded on objective game-readiness + do-no-harm, not absolute form by a noisy judge.

## 1. Why

The altimeter graded this postprocessor on **absolute form** via a single 5-lens LLM judge over 7 items
(SEM ≈ 0.7 — blind below ~1.5 points). That eval (a) measured the generator's KPI, not the finisher's,
and (b) issued a build mandate that damaged good inputs while the noise masked the harm. We replace it with
a **deterministic, objective** signal that matches the tool's real job and needs no 2.5M-token judge run.

## 2. The new success signal (two objective axes)

**A. Readiness (did the finisher make it game-ready?)** — deterministic, pure geometry/data, reuses the
existing `feedback.quality` gate blocks. A per-stage boolean readiness across the pipeline's objective
gates: topology (quad_ratio ≥ T, ngons == 0, non_manifold == 0), UV (has_uvs, overlap == 0, stretch ≤ T,
texel density in band), material (pbr_maps_present, textures_within_size, atlas_ready), engine (tri /
material / texture budgets, LODs, collision), export (transform_applied, watertight, valid profile). This
is the un-gameable half — no LLM. `readiness = fraction of objective gates passed` (+ the per-gate detail).

**B. Preservation (did it do no harm to the inherited form?)** — objective, uses the WORKING isolated
silhouette eye. At `intake`, capture and store the object's multi-angle **silhouette masks** (flat-fill,
isolated, ortho3). At any later point, capture the current silhouettes and compute
`preservation = mean over angles of IoU(intake_mask, current_mask)` (binary mask = object pixels vs
background; `view_selected` framing normalizes position + uniform scale, so IoU reflects SHAPE/proportion
change, not framing). `preservation == 1.0` = form untouched; lower = the pipeline altered the silhouette.
A good finisher keeps preservation HIGH while readiness rises. This is objective pixel math — no judge.

## 3. The do-no-harm guard (the fix for what the form-craft wave did)

A pipeline guard: after a stage's mutation, compute preservation vs the stored intake silhouette; if it
drops below a floor (e.g. `preservation < 0.85`, per-class tunable — a real shape change, not AA noise),
**auto-`session.revert`** that stage and record `harm_reverted`. This makes "do no harm" structural: the
smoothing/resize damage (barrel 6.6→4.5) would have been auto-reverted. Retopo legitimately changes
topology but should PRESERVE silhouette (retopo that drops preservation is bad retopo) — so the guard is a
correct, general invariant for a finisher. (Intentional form change on a `from_scratch` construct is a
separate, deferred mode exempt from the guard.)

## 4. The objective benchmark runner (replaces the judged altimeter)

A new runner scores each benchmark item **deterministically**: drive the item through the pipeline
(the agent still does the finishing work), then compute `{readiness, preservation, per_stage_gates,
harm_reverts}` — pure Python + the silhouette eye, **no LLM judge panel**. Dramatically cheaper and
reliable (the scoring is deterministic; only the finishing agents cost tokens, and there is no ±0.7 judge).
Report `{mean_readiness, mean_preservation, per_item, n_fully_ready}`. Success = readiness up, preservation
held ≥ floor. The old judge-based `altimeter.mjs` is retired for grading (kept only if a perceptual
spot-check is ever wanted, clearly labeled non-primary).

## 5. Components to build

1. **`feedback.silhouette_masks` / preservation metric** — a pure-Python IoU over two sets of silhouette
   PNGs (decode → binary mask by luminance threshold → IoU per angle → mean). Offline-testable with
   synthetic masks; the render half reuses the isolated silhouette eye.
2. **Pipeline intake-silhouette capture + preservation check** — `pipeline.start` captures & stores the
   intake silhouette reference (base64 or a compact mask); a `pipeline.preservation(object)` read-only tool
   returns current preservation vs intake.
3. **Do-no-harm guard in `advance`/stage-mutation** — after a mutating stage, if preservation < floor,
   auto-revert + flag. (Reuses `session.checkpoint`/`revert` already at stage entry.)
4. **`feedback.readiness(object)`** — a read-only tool bundling the objective gate results across stages
   into a single readiness scorecard (composes existing `feedback.quality` + `stage_gates`).
5. **Objective benchmark runner** (`workflows/readiness.mjs` or a Python harness) — per item: drive pipeline
   → compute readiness + preservation → aggregate. No judge panel.

## 6. What we keep / retire / defer

- **Keep:** the isolated silhouette eye, `feedback.quality`/gates, `form_critique` (as an agent aid),
  `fill_ratio`, checkpoint/revert. All sound.
- **Retire (for grading):** the absolute-form 5-lens judge panel in `altimeter.mjs` as the primary metric.
- **Bury:** the smoothing/resize form-craft verbs (stay on the dead `layer2-form-craft` branch).
- **Defer:** from-scratch surgical form CONSTRUCTION (needs a spatial-addressing layer) — separate later wave.

## 7. Success criteria

- `feedback.readiness` and `pipeline.preservation` computable offline (synthetic) + live.
- The do-no-harm guard auto-reverts a stage that damages the silhouette (proven by a test where a
  smoothing op drops preservation → the guard reverts it).
- The objective benchmark runner produces `{mean_readiness, mean_preservation}` deterministically; on the
  7 items the current pipeline reports high preservation (it no longer damages form) and its true readiness.
- No LLM judge in the primary grade.

## 8. Open decisions (for review)

1. **Preservation floor** — 0.85 global vs per-class? (Lean: start 0.85 global, tune per class later.)
2. **Preservation storage** — store intake silhouette PNGs vs compact binary masks in run state? (Lean:
   compact masks — smaller, deterministic.)
3. **Runner form** — `.mjs` workflow vs a pure-Python live harness? (Lean: Python harness — scoring is
   deterministic, only pipeline-driving needs an agent; simpler + cheaper than the judged `.mjs`.)

---

## 9. Correction — measure-and-flag (red-team-driven, 2026-07-02)

An adversarial red-team of the first plan found the auto-revert guard architecturally conflicts with the
pipeline's own job (retopo/LOD *intentionally* reduce geometry; a cumulative silhouette-vs-intake guard
would deadlock required stages), and the silhouette mask fails open. These corrections are binding and
supersede §3's hard guard.

1. **Do-no-harm is MEASURED, not enforced by auto-revert.** Drop the pipeline auto-revert guard entirely;
   `pipeline.advance` stays `mutates=False`. Preservation is a **metric** computed **per-stage delta**
   (current vs the PREVIOUS stage-entry silhouette, with a stage-appropriate budget — repair/uv expect
   ~0 silhouette change; retopo/optimize/LOD are allowed a larger budget) **and** cumulative-vs-intake for
   reporting. A stage exceeding its budget is **flagged** (`harm_flagged` in the scorecard), not reverted —
   the agent/eval acts on the flag; the pipeline never deadlocks.
2. **Robust, fail-closed mask.** Render the preservation silhouette with `render.film_transparent = True`
   and threshold the **ALPHA** channel (object coverage) — invariant to world/lighting/AgX tone-mapping,
   which the RGB-luma mask was not. Use a **fixed camera framing** derived once from the stored intake bbox
   (NOT per-render `view_selected`, which reframes on any bbox change and hides uniform-scale changes) and
   **ortho-only** views (`ortho3` = front/right/top; exclude `persp` foreshortening). Fail **closed**:
   return `available:false` when object/background aren't cleanly separable (histogram/coverage check), and
   also carry a cheap GL-free **bbox aspect/scale** delta alongside IoU so a uniform-scale change is still
   visible.
3. **Readiness dedup.** Compose `feedback.readiness` as the mean of per-STAGE pass-fractions (equal weight
   per stage/axis) AND the raw deduplicated-gate fraction (repeated paths like `topology.non_manifold_edges`
   counted once); report both.
4. **Honest runner.** Fix tool names (`object.rename`, not `objects.rename`; derive the created object name
   from the `scene.create_object`/`object.create` result, not a non-existent `scene.info["active"]`). The
   runner needs a real (cheap) finishing agent per item to actually produce a finished asset before scoring;
   scoring is deterministic (no LLM judge). Add a startup registration guard asserting every tool the runner
   calls exists. Distinguish **unmeasured** (headless / non-separable) from **failed** in the aggregate
   (`n_unmeasured` excluded from means), so a headless run reports honestly instead of catastrophically.
5. **Discoverability.** Surface `feedback.readiness` (game-ready check) and `pipeline.preservation`
   (do-no-harm check) to the finishing agent via `src/niua_blender_mcp/prompts.py` (and the modeling playbook).
