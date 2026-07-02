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
