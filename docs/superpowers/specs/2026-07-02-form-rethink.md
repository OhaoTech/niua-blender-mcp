# Form Rethink — Resolving the Five Lenses into One Direction

**Date:** 2026-07-02
**Status:** Strategic decision doc. Supersedes the form-craft wave's premise (`2026-07-02-layer2-form-craft-design.md`) and the baseline's "lead with form" reprioritization (`altimeter-baseline.md §Implication`). Re-endorses and re-sequences the original finish-line roadmap (`2026-07-01-layer2-finish-line-roadmap.md`).
**Inputs:** five lens analyses (modeling-process, product-scope, data-evidence, technical-alternatives, eval-redesign) + altimeter baseline + form-craft design + finish-line roadmap.

---

## 1. The honest finding

**Form-craft-via-composite-verbs is disproven — theoretically, mechanistically, and empirically. The perception scaffolding is sound and stays.** All five lenses converge here; there is no dissent.

- **It is a category error in the operator's math, not a tuning miss.** The three "craft" verbs are information-*destroying* global operators: `proportion_adjust` → affine `resize` (can stretch masses, cannot add them); `silhouette_refine` → Laplacian `vertices_smooth` (a low-pass filter that provably removes the high-frequency content — edges, ridges, belly-to-stave transitions — that *is* the form); `reblock_form` → `remove_doubles` + smooth. This verb set spans a space containing **zero believable objects**: you can only make the input blurrier or stretchier. Iterated, every mesh converges to its own average — a featureless blob.

- **The data is the fingerprint of exactly that, applied indiscriminately.** Good-down / bad-up / mean-flat: barrel 6.6→4.5 ("featureless pebble"), shell 5.8→3.2, pumpkin 5.1→3.1 (real damage — smoothing erased real form); blob 1.6→5.7 (de-noised into an inoffensive lump). The blob **overshot the mean by +1.76**, which regression-to-the-mean *cannot* produce — proving the intervention has large, real, causal effects on the object, which in turn proves the symmetric drops on good items are **real damage, not measurement noise**. The rising bad-item score is variance compression (blandification), not craft.

- **The smoking gun: `material_read` regressed 4.00→3.36** — the single largest per-lens move in the whole comparison, in the wrong direction, on a lens the wave never targeted. Smoothing killed the surface micro-relief the material lens reads off. The "form" verbs weren't even form-neutral; they were net-destructive. **The tool damaged the one form-adjacent lens it genuinely owns while chasing form it does not.**

- **What is proven-sound and must be kept:** the isolated multi-angle silhouette eye (front/right/top ortho), the real scale-invariant `fill_ratio` (bmesh solid volume / bbox volume), `feedback.form_critique` as an observe-and-judge call, the degenerate guards, and the checkpoint/revert machinery. These are *measurement and safety*. The eyes are right; the hands (the verbs) were the exact opposite of modeling.

- **A second, independent failure worth naming:** the verbs ran **fire-and-forget, universally, even on already-good inputs, with no per-edit "did this help?" acceptance test.** The checkpoint machinery existed but nothing reverted an edit that *lowered* the score. A destructive op with no perceptual acceptance test is guaranteed to damage anything above the mean. This is the do-no-harm gap, and it is cheap to close.

- **The meta-lesson (eval-redesign's sharpest point, and correct):** this was an **evaluation failure that manufactured an implementation failure.** The altimeter graded *absolute* form on a noisy single-run judge, announced "silhouette is the weakest lens," and issued a build mandate. The team built form verbs; the verbs damaged the good inputs the benchmark had no way to protect (a −2.1 barrel drop was indistinguishable from "needs more craft"). Fix the instrument before building anything else.

---

## 2. The core strategic decision

**This tool is a technical FINISHER (postprocessor), not a form CREATOR.** Its professional identity is *senior technical artist / game-asset finisher*, not senior sculptor. It **elevates and preserves the form it is handed; it does not re-author it.** One narrow, explicitly-separated exception (from-scratch blockout) is a mini-generator and is treated as such.

The decisive reasoning, adjudicating the one real disagreement between the lenses (modeling-process/technical-alternatives lean "agent can create form"; product-scope/eval-redesign say "form is a category error here"):

The disagreement dissolves once you **split by input class**, which is what the evidence demands:

| Operation | Verdict | Why |
|---|---|---|
| **PRESERVE form** through technical transforms (retopo, decimate, LOD, bake, UV) | **OWN it — core charter** | Output form tracks input form (barrel good-in→good-out; blob none-in→none-out). Fully gate-able as a *fidelity* check, not a taste check. This is where the perception layer's real value lives. |
| **CONSTRUCT form from scratch** (brief → blockout from primitives) | **A separated mini-generator mode; bounded experiment** | The best item (barrel 6.6) is exactly this path. It works because it is *additive*, and because the brief *is* the intent (no forbidden niua knowledge needed). Legitimately viable — but it is an *upstream-flavored* act, not finishing, and must not be smeared across the postprocess pipeline. |
| **RE-AUTHOR existing form** (smooth/resize a barrel into a "better" barrel) | **NOBODY — it is a mirage. Kill it.** | Destructive-only on existing geometry; damages the generator's output; and doing it *well* requires the intended-design intent, which is upstream knowledge this decoupled tool is forbidden to hold. This is bucket 3, and it is what the wave died on. |

**Adjudication of the split:** For the 6-of-7 benchmark items that are cleanup/existing-form, the finisher camp wins decisively — every re-authoring attempt damaged the input, and re-authoring needs intent the tool cannot have. For the 1 from-scratch item (a real product path: roadmap W3.3), the modeling-process camp is right that *additive, spatially-addressed, per-edit-governed* surgical modeling is the correct method and the barrel proves it — but it is a **separate, bounded, de-risking experiment, not the main line.** The clean line is: **from-scratch is fine because the brief carries the intent as input; existing-form re-authoring is not, because the intent is absent.**

### What this tool OWNS (all deterministic, all preserving of inherited form)
Retopo / clean quad flow / poly budget · UV (minimal-distortion unwrap, texel-density uniformity, seams, packing) · **real high→low bake** (cage/projection/ray for normal/AO/curvature/thickness, bake-quality gates) · **real layered PBR materials** (texel-correct, lookdev) · LOD chains that hold silhouette · collision proxies · correct scale/orientation/pivot · engine-clean glTF export · repair of *degenerate* geometry (non-manifold, holes, flipped normals — technical, not aesthetic).

### What this tool must NOT do
Invent primary form the generator failed to produce (blob rescue) · re-proportion or re-silhouette an existing asset toward "more believable" · any operation whose success is judged by a form-taste panel rather than an objective delta.

---

## 3. The redesigned success signal

**Replace the single blended, judge-derived 0–10 with two objective scores plus one tightly-scoped, noise-controlled perceptual diff. Nothing in the primary gate uses an LLM.** This directly fixes the instrument that issued the wrong mandate, and it is cheap enough to gate every PR instead of spending 2.5M tokens to find out a change regressed.

### 3A. READINESS — objective technical game-readiness (deterministic, no judge)
Per item, compute and threshold: quad ratio / n-gon count / non-manifold=0 / watertight-if-required · tri budget · LOD chain present & monotonic · UV coverage / no unintended overlap / **texel density in band AND low cross-island variance** / no flipped UVs · **real bake error** (angular normal RMS + 95th-pct vs high-poly reference; cage fit; ray-miss/black-AO count) · PBR validity (value ranges, color space) · real-world scale + transforms applied + correct up/forward axis · **Khronos glTF validator zero errors** · **headless Godot import clean.** This is ~80% of "production-ready," un-gameable, CI-able, zero tokens. The baseline already passes 7/7 objective gates — this is the floor you can lean your full weight on; extend objective capability *here*, because you'll actually be able to see it move.

### 3B. DO-NO-HARM PRESERVATION — the one perceptual thing the tool owns, as a diff not a verdict
Render multi-angle silhouettes of **INPUT vs OUTPUT** (reuse the working eyes), normalize scale/orientation, and compute objectively: **silhouette IoU/Chamfer**, **proportion drift** (bbox aspect + primary-mass distribution), **detail retention** (curvature-histogram / high-frequency energy — catches "smoothed to a pebble" directly), **volume preservation** (reuse `fill_ratio`). Aggregate as **Preservation = min(silhouette, proportion, detail, volume)** — the `min` means one collapsed axis tanks the score, so you cannot hide a pebble behind good UVs. **This is the metric that would have caught the barrel→4.5 collapse the instant it happened.** It inverts the failed wave's incentive: it *penalizes* form destruction and rewards technical improvement at constant form.

### 3C. Pass rule (per item)
Passes iff: all hard READINESS gates pass, AND Preservation ≥ threshold (e.g. silhouette IoU ≥ 0.90 for declared-clean inputs, ≥ 0.70 for declared-messy), AND continuous technical metrics in band (bake 95th-pct < X°, texel uniformity above threshold). Headline number = **pass_rate**, made entirely of individually-true-or-false facts.

### What to STOP trusting
1. **The mean-of-7 as a gate.** SEM ≈ 0.73; a reported 3.94→3.90 (Δ −0.04) is ~1/18th of a standard error. It cannot resolve anything below a ~1.0–1.5-point shift. Altitude read only, never pass/fail.
2. **Per-lens rank order** ("silhouette is weakest"). The entire spread of the five lens means is 0.42 — *smaller than the SEM*. The lenses are ~one latent factor plus noise; "silhouette is the bottleneck" is the right hunch held too hard, and it is what mis-issued the mandate.
3. **Any single-run delta** without ≥2 runs establishing run-to-run variance (the spec demanded this and it wasn't done). Report effect sizes with error bars or don't report them.
4. **"Raising the bad items" as progress** — confounded with regression-to-mean and with blandification.
5. **The +1.0-per-lens judge-delta exit gate** — it lives entirely inside the noise floor.

### The LLM judge's demoted role
It produces **no gating number.** At most it is an *offline* diagnostic, and only as **relative A/B** ("INPUT vs OUTPUT: improved / unchanged / damaged, on which axis" — far less noisy than an absolute scale), N-run median + IQR at temp 0 with a fixed render seed and pinned calibration anchors. Fix render determinism so baseline and post are comparable at all.

---

## 4. The concrete next direction (ranked)

Ordering principle: **fix the instrument first (it steers everything), then build the gate-able ceiling the tool owns, then optionally de-risk the one legitimate form-authoring path.**

### #1 — Fix the success signal + ship the do-no-harm guard *(cheap, deterministic, do first)*
Build §3's Readiness + Preservation eval. Add the **do-no-harm guard** as a live pipeline invariant: *postprocess may never lower intake silhouette / proportion / detail / volume metrics* — any stage that would is auto-reverted to its pre-edit checkpoint. This reuses only the perception layer that already works, deletes the good-down half of the failure signature outright (it would have blocked the 6.6→4.5 / 5.8→3.2 / 5.1→3.1 regressions), and stops the roadmap from being steered by a noisy judge. **Do this before spending another 2.5M-token run.**

### #2 — Real bake + real materials (the original Phase-1 ceiling) *(highest-confidence capability lever)*
Return to the finish-line roadmap's Phase 1: real high→low bake (cage/projection/ray + bake-quality gates) and real layered PBR + lookdev. This is the **gate-able ceiling the tool genuinely owns**, it is exactly where `material_read` — the lens the wave *regressed* — is legitimately raised (crisp normals, edge/curvature bake read as intentional form and design), and every gain is objectively measurable so you'll know it moved. The baseline's "lead with form instead of bake" reprioritization was a misread of the tool's own data; this re-endorses the pre-panic roadmap.

### #3 — Bounded from-scratch surgical-modeling experiment *(real build, separated mode, not the main line)*
The *only* form-authoring path with evidence behind it (barrel 6.6, the best item). Scope it to a **separate from-scratch/blockout mode**, prove it **constructively on `from_scratch` only** (cube → barrel/crate), and **never point it at blob-rescue.** It is gated on three pieces of missing infrastructure the wave never had:
- a **spatial selection / element-query layer** — `mesh.query` returning per-element {index, centroid, normal, area}, and `mesh.select_by` predicates (normal direction, position/bbox-fraction, feature-angle, loop/ring, grow/shrink). Today selection is raw-integer-index only, so the agent cannot translate "bevel the top rim" into a reliable selection — *this* (not the operator set) is what would make a surgical loop thrash;
- **wiring `loopcut`** (bmesh subdivide-edgering — it's in the Blender manifest but never wired as a verb) and a **`move_selection(vector)`** so masses can be nudged without extruding;
- the **per-edit perceptual accept/revert governor** as the non-negotiable control law: perceive → decide ONE additive move → select spatially → apply ONE op → re-perceive → keep iff silhouette-vs-reference delta improved, else auto-revert. This turns "blunt verbs that damage good inputs" into a monotone hill-climb that cannot score below its start. Budget ~30–80 tool calls / ~10–25 perception checkpoints per asset — within an agentic budget. **This is a de-risking experiment for roadmap W3.3, explicitly deferred behind #1 and #2.**

### #4 — Push form upstream (finding + intake triage gate) *(highest leverage on the actual root cause, but out of this tool's hands)*
Emit the finding to the generator team: *a postprocess finisher cannot manufacture senior form from a fundamentally malformed input; `generated_blob` (1.6) is out of scope, and the blob 1.6→5.7 "win" is the failure mode dressed as a success.* In-scope and decoupled: add an **intake triage gate** that *classifies* inputs (finishable / needs-regeneration) and lets the tool **decline formless input and route it back**, rather than heroically smoothing noise into a smooth nothing. This judges the mesh, not niua — no coupling.

### What to SALVAGE from the unmerged form-craft branch
**Keep (repurpose):**
- `feedback.form_critique` — repurpose from *creation target* to (a) the input-vs-output **preservation diff** (§3B) and (b) the eye for the #3 from-scratch loop.
- `fill_ratio` (real bmesh solid volume / bbox) — sound measurement; becomes a Readiness metric + the volume-preservation axis.
- Multi-angle isolated silhouette capture (already on `main`) — the whole preservation metric reuses it.
- Degenerate guards (non-manifold / zero-area / extreme-aspect) — fold into Readiness gates and the intake triage (#4).
- Per-subject reference proportion targets (target+tolerance) — anchor for the #3 from-scratch loop and the proportion-preservation reference.
- Checkpoint/revert machinery — becomes the do-no-harm guard (#1) and the per-edit governor (#3).

**Kill:**
- `model.proportion_adjust`, `model.silhouette_refine`, `model.reblock_form` — empirically + mathematically disproven form actuators.
- The **blockout stage as a universal pipeline gate** running on all inputs — it smears form authoring across the postprocess. Reserve blockout for the separated from-scratch mode (#3).
- The `+1.0-per-lens` judge-delta exit gate — noise-floor astrology.

---

## 5. Decision points for the human

**DP-1 — Ratify the identity.** Adopt "technical finisher that *preserves* form + a separated from-scratch mini-generator" as the charter, and formally kill generic form re-authoring of existing assets?
- *Recommended: YES.* The alternative (keep pushing this tool to be a general form creator) is disproven by the data and violates the decoupling contract. **The cost of NO is a tool that can lower a 6.6 to a 4.5 — a liability in the toolchain.**

**DP-2 — Sequencing & spend.** Do the eval redesign + do-no-harm guard **first** (cheap, deterministic) and gate all future work on it, **deferring the next 2.5M-token altimeter run** until the instrument is fixed — versus proceeding straight to real bake/materials on the current noisy judge?
- *Recommended: eval + guard FIRST.* The eval is the thing steering the roadmap and it steered it into a wall once already. Fixing it is days, not weeks, and it makes every subsequent wave measurable per-PR.

**DP-3 — Fund the from-scratch experiment now, or later?** Build the spatial-selection layer + `loopcut` + `move_selection` + per-edit governor now (real new infra) to de-risk W3.3 — or shelve it until Phase 1 (bake/materials) lands and only build it when from-scratch briefs are actually on the product's critical path?
- *Recommended: LATER (shelve behind #1 and #2).* It is the only form path with evidence, but it is a genuine research build, and 6 of 7 benchmark items don't need it. Do it when from-scratch is on the critical path, not to chase a benchmark average that mostly measures the generator.

---

## Executive summary

The double-red-teamed form-craft wave is a clean, decisive **negative result**: hand-authored composite *smoothing/resize* verbs cannot create form — they are information-destroying operators that mathematically can only blur good inputs toward a bland mean (barrel 6.6→4.5, shell 5.8→3.2, pumpkin 5.1→3.1) while de-noising bad ones (blob 1.6→5.7), even *regressing* the one form-adjacent lens the tool owns (`material_read` 4.00→3.36) — and the "flat mean" only *looks* neutral because a single judge over 7 items (SEM ≈ 0.73) is blind below ~1.5 points. The perception scaffolding (isolated multi-angle silhouette eye, real scale-invariant `fill_ratio`, `form_critique`, checkpoint/revert) is sound and stays. Resolving all five lenses: this Blender MCP is a **technical finisher that PRESERVES the form it is handed, not a form re-author** — form CREATION belongs to the generator (or a separate, brief-driven from-scratch mini-generator mode), form RE-AUTHORING of existing assets belongs to nobody, and the altimeter's absolute-form grade was measuring the wrong tool and issued the wrong build mandate.

**Single strongest recommendation:** **Fix the success signal first — replace the noisy absolute-form judge with deterministic Readiness gates plus an objective input-vs-output "do-no-harm" preservation metric (reusing the working eyes), and enforce a do-no-harm guard that auto-reverts any stage that lowers intake form — then return to the original Phase-1 roadmap (real bake + real materials), which is the gate-able ceiling this tool actually owns and the lens the wave regressed.** Bury the smoothing/resize verbs; keep the eyes.
