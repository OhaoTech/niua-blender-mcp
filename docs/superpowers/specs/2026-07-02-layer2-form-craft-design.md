# Layer 2 — Form-Craft Wave Design

**Date:** 2026-07-02
**Status:** Design (for review) — build deferred to a fresh session.
**Depends on:** Perception layer (all eyes working + isolated, on `main`); the altimeter (baseline 3.9/10).

## 1. Why this wave

The altimeter baseline is unambiguous: the pipeline drives any input to a **gate-passing, exported**
asset, but the result is **amateur in FORM**. Per-lens means:

```
silhouette 3.79  ← weakest    (FORM)
proportion 3.86               (FORM)
design     3.86               (FORM)
material   4.00
topology   4.21  ← strongest  (what the pipeline already gates)
```

The three weakest lenses are all **form** — the pipeline is best at what it can gate (topology) and
worst at making things *read as believable objects*. `hard_surface` scored worst by class (2.8)
despite the most craft verbs; the "cleanup" cases were worst of all (recovering valid topology from
a noisy blob does not recover coherent form). **Raising form is the single highest-value lever
toward senior.**

## 2. The core principle

**Form is perceptual/judgment, not gate-able.** You can gate `quad_ratio == 0.95`; you cannot gate
"reads as a believable barrel." So this wave is NOT "add form gates." It is: **let the agent carry
form judgment (it's taste), and scaffold it with (a) perception it can trust — now built, (b) a
disciplined process that establishes form before detail, (c) capability to fix form, and (d)
grounded reference to anchor the judgment.** This is the agent-as-artist axis, applied exactly where
the data says it's needed, using the perception layer we just fixed.

## 3. Components

### 3.1 Form self-critique tool (the in-loop judge)
`feedback.form_critique(object)` — the OBSERVE-and-judge call for form. Bundles: multi-angle
**silhouette** renders (now working) + `feedback.quality` proportion/symmetry metrics + the task
brief + the asset-class **reference proportion targets** (§3.4). The agent reads it and critiques
its OWN form: are proportions believable vs the reference? does the silhouette read cleanly from all
angles? does the form have clear primary masses? It returns a structured critique + concrete fixes.
This is the altimeter's judge repurposed as an *in-loop self-correction* step — the agent supplies
taste; the silhouette eye + reference targets keep it honest. Iterates via `session.checkpoint`/
`revert`. (Reuses the working eyes; no new render tech.)

### 3.2 Blockout-first stage discipline
Add a **`blockout`** gate early in the pipeline (after `repair`, before `retopo`): the asset cannot
advance to detailing until it clears a form check = objective proportion sanity (aspect ratio /
bbox proportions within the asset-class's believable range) **AND** a `form_critique` pass the agent
must satisfy. This forces the senior "block out the primary forms and proportions first" discipline
— the thing the blob (1.6) never did. The objective half is gate-able (proportion ranges); the
perceptual half is the self-critique.

### 3.3 Form-craft capability (verbs / workflows)
The agent needs MOVES to fix form, recommended by `craft_workflow.recommend` at blockout/repair:
- **Proportion adjustment** — scale primary features toward believable ratios (guided by reference).
- **Silhouette refinement** — adjust the outline-defining geometry so the form reads.
- **Blockout construction** (from-scratch) — build primary masses from primitives.
- **Form-recovery** (the hard case) — for noisy/generated inputs, rebuild coherent form: remesh to a
  clean base → re-block the primary forms → detail, instead of cleaning noise in place. A
  `model.reblock_form` verb / a `generated_cleanup` form-recovery workflow. This is what moves the
  blob (1.6) and generated_cleanup (3.7).

### 3.4 Reference proportion targets (grounding)
Extend the asset-class profiles with **form/proportion reference targets** distilled from real
senior practice (cite sources): e.g. crate ≈ cubic (aspect ~1:1:1); barrel ≈ 1:1:1.2 with a belly
curve; believable real-world scale per class. These anchor the `form_critique` (objective-ish
comparison) and guide the agent. Curated/reviewed — not grown.

### 3.5 Form knowledge pack
A `knowledge` pack on senior form principles (blockout-first; silhouette must read from all angles;
primary→secondary→tertiary forms; believable mass and proportion; where form goes wrong) that the
agent consults during form-craft, loaded like the existing stage knowledge packs.

## 4. How it uses the (now-working) perception

`form_critique` renders the **multi-angle silhouette** — the agent SEES the form from front/side/top/
persp (all distinct + isolated now that capture is fixed) + reads proportion/symmetry numbers,
compares against the reference targets, and self-corrects. This wave is only viable *because* the
capture bug is fixed; on the old broken eyes the agent would have judged form from collapsed/blank
renders.

## 5. Build sequencing (sub-waves, for the later plan)

- **W-form-a:** `feedback.form_critique` tool + reference proportion targets in asset classes + form
  knowledge pack. (Perception + grounding; mostly additive, testable.)
- **W-form-b:** blockout-first stage + gate (proportion sanity + form_critique) in the pipeline.
- **W-form-c:** form-craft verbs/workflows (proportion adjust, silhouette refine, blockout,
  form-recovery), wired into `craft_workflow.recommend`.
- **Re-measure:** re-run the altimeter (~2.5M tokens) — the honest lift check.

## 6. Success criteria (from the finish-line roadmap, Phase-1 exit)

- `pass_rate > 0` (at least one item reaches a genuine senior ≥ 7.0), and
- `mean_overall ≥ 5.5`, and
- **`silhouette` is no longer the weakest lens** (form is no longer the bottleneck).

## 7. Open questions for review (decide before the build plan)

1. **`form_critique` as its own tool vs. extending `pipeline.self_critique`?** (Lean: its own tool,
   so it's usable outside the pipeline too.)
2. **How hard is the blockout gate?** Block advancement (strict, forces discipline) vs. advisory
   (warns but lets pass)? (Lean: block, with the objective proportion sanity as the hard part and
   `form_critique` as agent-satisfied.)
3. **Form-recovery scope** — full remesh+reblock (ambitious) vs. a lighter "re-establish primary
   proportions" pass first? (Lean: lighter first, measure, then deepen.)
4. **Reference targets** — how many asset classes / how detailed for v1? (Lean: the 4 existing
   classes, coarse proportion ranges, deepen later.)

## 8. Risks

- **`form_critique` is a judge** → anchor it with objective proportion metrics + reference targets so
  it's not pure vibes; keep the altimeter's objective gates as the floor.
- **Form-recovery could destroy detail** → run on a checkpoint; keep the original recoverable.
- **Over-fitting to the benchmark** → the altimeter's inputs are held-out; measure generalization,
  don't hand-tune per item.

---

## 9. Revision — red-team-driven corrections (2026-07-02)

An adversarial 6-lens review of the first implementation plan found a design-level flaw; these
corrections supersede the conflicting parts of §3 and §6. **Root problem:** an objective
bounding-box gate cannot capture "believable form" — `boxiness = bbox_volume/longest³` is pure
bbox shape (a spindly cross, a hollow shell, and a solid cube all ≈1.0), so it is blind to the
bad-form cases it targets and wrongly blocks legitimate elongated inputs. Form is perceptual (§2);
stop trying to hard-gate it.

**Corrected decisions:**

1. **Blockout gate = degenerate guard + enforced observation, NOT a proportion-quality gate.**
   The objective half only catches *broken* meshes: a real **mesh-fill-ratio** (bmesh solid
   volume / bbox volume — catches collapsed/spindly/hollow) with a low floor, plus an extreme-aspect
   degenerate guard. The enforced half: the pipeline requires a **recorded `feedback.form_critique`
   observation** on the object at `blockout` before `advance` (a state flag proving the agent looked
   — not a taste bar). Believable form is agent-carried and **measured by the altimeter's
   silhouette/proportion/design lenses**, not fake-gated. This must NOT block any of the 7 benchmark
   items at intake — add a test asserting each passes its degenerate guard.

2. **Add a real fill metric.** `feedback.quality` gains `fill_ratio` (bmesh solid volume / bbox
   volume; degrade to null if bmesh volume unavailable). Prove on known meshes it separates a solid
   box (~1) from a thin cross / collapsed blob (low). `boxiness` stays but is renamed in docs to
   "bbox cubeness" and is NOT described as fill.

3. **`form_critique` is data-driven + structured + wired in.** It interpolates *measured* aspect/
   fill/symmetry vs a **per-subject target + tolerance** (not wide class ranges; drop the dead
   aspect lower bound) and returns a structured object `{reads_all_angles, proportion_ok,
   primary_masses_ok, fixes:[…]}`. Default preset = **ortho-only (front/right/top)** for proportion
   reading (drop persp — perspective distorts proportion). It MUST be wired into
   `workflows/altimeter.mjs` (finish prompt observes form via `feedback.form_critique` at blockout
   and iterates before advancing) and instrumented (count calls per item) so the re-measure proves
   the intervention was exercised.

3b. **Reference targets carry target+tolerance per subject** (e.g. crate target_aspect≈1.0 ±; barrel
   ≈1.2 ±), not permissive [min,max] class bands.

4. **`reblock_form` is checkpoint-safe by mechanism, not by warning.** Auto `session.checkpoint`
   BEFORE the first mutating op; on ANY op exception, `session.revert` then re-raise (no partial
   destructive mutation). Merge distance is **bbox-relative** (fraction of bbox diagonal, clamped),
   never absolute — arbitrary-scale generated meshes must not collapse. Return the checkpoint label;
   `postcheck_recommended` includes `session.revert`. Tests: force a mid-op failure → mesh
   byte-identical; live smoke: checkpoint→reblock→revert restores vert count/bbox.

5. **`silhouette_refine` is silhouette-aware.** No uniform smoothing of hard-surface corners
   (it degrades the crisp silhouettes hard_surface depends on) — smooth only boundary/feature-angle
   loops, or exclude hard_surface. Verify per-class the blockout_pass does not LOWER objective
   metrics.

6. **Success criteria re-scoped (was arithmetically unreachable).** This wave targets 3 of 5 lenses;
   `mean_overall ≥ 5.5` is impossible from form alone (max ≈5.1) and a bare `weakest_lens` rank-flip
   is within judge noise (0.07 margin). New exit gate: **per-lens deltas vs a recorded baseline —
   silhouette AND proportion each +≥1.0**, with baseline+post each run **twice** (or determinism
   fixed) so the lift exceeds run-to-run noise. `mean_overall ≥ 5.5` is a later cumulative target,
   not this wave's gate.

7. **Coverage/parity fixes:** the blockout stage insertion breaks **five** real-Blender smoke walks
   (not one) — update all. Add an offline `_GATES` server↔addon equality test (mirroring
   `_PACKS`/`_WORKFLOWS`). Add offline fake-bpy `gate_check(stage='blockout')` tests for BOTH an
   in-range pass AND an out-of-range/degenerate reject. Scope `generated_cleanup.form_recovery_reblock`
   to `['blockout']` (repair is topology) or add an explicit recommend-order test.
