# Layer 2 — The Finish-Line Roadmap

**Date:** 2026-07-01
**Status:** Strategy (approved direction) — supersedes the open-ended wave stream
**Purpose:** Turn "how many waves remain?" from *uncountable* into a defined, finishable
list, by narrowing the goal and changing what a "wave" is.

---

## 1. The decision this roadmap encodes

Two goals were on the table:

- **Senior artist (general):** taste + any brief across sculpt/rig/anim/sim/light/render/…
  → open-ended, **100+ waves, never "done."**
- **Senior game-asset finisher (niua's actual job):** take any input the generator
  produces (or a from-scratch brief) → a **Godot-ready game asset**, autonomously,
  watchable in a visible Blender. → **countable and finishable.**

**We build toward the finisher.** It is exactly what niua needs, it is what the existing
gated pipeline was built for, and it has a real finish line. General artistry can be a
later, separate ambition.

## 2. The axis change (why the count shrinks)

The recent waves (8→10) hand-author a **recipe per {asset class × stage} cell**. That matrix
is ~48 cells for a realistic class set → **~30–40 recipe-waves, still brittle at the edges.**

Instead, the intelligence that generalizes is the **agent**. The scaffold's job is to make
the agent's own judgment *land reliably*: perception it can trust, objective gates it checks
itself against, grounded knowledge, and safe iteration. When the agent carries the long tail,
recipes stop being the path and become **optional accelerators** — a short, data-driven tail.

Result: two honest counts.

| Axis | Remaining waves | Finish line? |
|------|-----------------|--------------|
| Recipe-per-cell (current drift) | ~30–40, growing | No — unbounded |
| **Agent-judgment + real subsystems (this roadmap)** | **~18–22** | **Yes — defined below** |

## 3. Definition of Done (the finish line)

Layer 2 is **done** when, for a **held-out benchmark of diverse inputs** (varied asset types,
messy generated meshes, and from-scratch briefs the system has never seen), the
MCP-driven agent autonomously produces assets that:

1. **Pass all objective gates** at every stage (topology, UV, bake, material, optimize, export).
2. **Score ≥ the senior threshold** on the perceptual **altimeter** (§4) — judged against
   reference for silhouette, proportion, believability, design intent, and material read —
   **not** merely gate-pass.
3. **Hold across held-out asset classes with no class-specific recipe** (generalization proof).
4. Use **real high→low bake** and **real material/lookdev authoring** (not slot-readiness).
5. Run **fully autonomously**, end-to-end, **in a visible Blender**.

If all five hold on the held-out set, the finisher is senior-grade and the roadmap is complete.

## 4. What exists vs. what's missing (grounding)

**Built (Waves 1–9B, on main):** gated pipeline (9 stages), perception eyes, objective
`feedback.quality` gates, asset-class profiles (4), `craft_workflow.recommend → verb → gate`,
knowledge packs, checkpoint/rollback. ~73 Layer-2 tests green.

**Specced only:** Wave 10 (`surface.*`, uv→bake→material recipe for one class).

**The real gaps between "passes gates" and "senior":**
- **No altimeter.** Gates measure a *technically valid* asset, not senior *quality*. The old
  `evals/` battery + judge stub + `converge_modeling.mjs` are **vestigial** — one crate, a
  stub score. There is currently **no instrument that measures the goal.**
- **Bake is faked.** The "bake" stage checks map-*slot* readiness, not real high→low
  projection/cage/ray. This is a quality ceiling.
- **Materials are slot-readiness.** No real lookdev-judged PBR authoring.
- **Perception unproven at scale.** The eyes are unit-tested + headless-enveloped, but
  correct *rendering* in a visible Blender hasn't been re-validated broadly (the bug class
  that cost a 1M-token run).

## 5. The roadmap (phases → waves)

Ordering principle: **measure before building; build the ceiling before the tail.**

### Phase 0 — Consolidate & measure (build the altimeter FIRST)

You cannot climb a hill you can't see. Also retire the vestigial old-loop scaffolding.

- **W0.1 — The Benchmark.** A diverse, held-out input set: N representative asset types
  (hard-surface prop, organic prop, mechanical/weapon, character-ish, environment chunk,
  foliage, modular kit) × input conditions (clean, messy-generated, from-scratch brief).
  Concrete meshes/briefs committed as fixtures. This is the exam.
- **W0.2 — The Altimeter.** A real perceptual senior-quality evaluator: multi-angle +
  overlay renders → calibrated multi-lens judge with explicit score anchors, scored against
  reference, returning a per-dimension senior score (not the stub). Re-validate the eyes
  render correctly across the benchmark (kills the render-bug class). Absorb/retire
  `evals/battery/modeling_prop`, the judge stub, and `converge_modeling.mjs`.
- **W0.3 — Baseline run.** Run the **current** pipeline against the benchmark. Produce the
  honest scorecard: overall senior score + per-stage / per-class failure map. Now every wave
  after has a number to move and a target to aim at.

### Phase 1 — The quality-ceiling subsystems (the real builds)

Where "passes gates" ≠ "senior" today. Sized as subsystems, not one-cell recipes. Re-run the
altimeter after each to prove it moved.

- **W1.1–W1.3 — Real bake.** High→low: cage generation, projection, ray bake of
  normal/AO/curvature/thickness from an actual high-poly source; bake-quality gates
  (silhouette delta, normal error, cage fit). ~3 waves.
- **W1.4–W1.6 — Real materials + lookdev.** Layered PBR authoring (base/wear/edge/dirt),
  texel-density-correct, lookdev turntable judged by the altimeter. ~3 waves.
- **W1.7 — UV seam intelligence + auto-retopo quality.** Beyond smart-unwrap/decimate:
  seam reasoning + quad-remesh/shrinkwrap retopo with topology gates. ~1–2 waves.

### Phase 2 — Generalization (make the agent carry the tail)

The axis change, proven.

- **W2.1 — Generalized stage solver.** Each stage becomes a driver the agent operates using
  eyes + gates + knowledge as its feedback loop, working on **any** input — not a
  class-specific recipe. Recipes become optional priors it may consult.
- **W2.2 — Held-out class proof.** Feed asset classes with **no recipe**. Require the agent
  to still pass gates + altimeter. Passing here is what breaks the recipe dependency —
  the core Definition-of-Done item #3.
- **W2.3 — Self-critique convergence.** The per-stage do→observe→gate→critique→revert loop
  runs to convergence autonomously, bounded, anchored by objective gates (not a noisy judge).

### Phase 3 — Short recipe tail + autonomy + product wiring

Only now, and only where the benchmark shows the agent struggling.

- **W3.1–W3.2 — Data-driven recipe tail.** Add the *few* class/stage recipes the baseline map
  proves measurably help as accelerators. Short and evidence-based, not the 48-cell matrix.
- **W3.3 — From-scratch blockout workflow.** Brief → blockout → into the pipeline.
- **W3.4 — Full autonomous run.** The whole intake→export pipeline end-to-end, unattended,
  in a visible Blender, on a benchmark item.
- **W3.5 — Product seam + hardening.** The generic `io` handoff to niua-godot (orchestration
  lives one level up, zero niua knowledge here); perf, failure recovery, docs.

### Finish-line gate

Run the held-out benchmark. Pass = DoD §3 items 1–5 all hold. That is "senior game-asset
finisher," and it is the end of Layer 2's core.

## 6. Wave count summary

- **Phase 0:** 3 waves (benchmark, altimeter+eye-revalidation, baseline).
- **Phase 1:** ~7 waves (bake ×3, materials ×3, uv/retopo ×1).
- **Phase 2:** ~3 waves (generalized solver, held-out proof, convergence).
- **Phase 3:** ~5 waves (recipe tail, from-scratch, autonomous run, product seam, hardening).

**Total: ~18 waves to a *defined* finish line** — versus an uncountable recipe stream. You can
now see the end from here.

## 7. What this means for Wave 10

Wave 10 (`surface.*` uv→bake→material recipe) is a **recipe-per-cell** wave. Under this
roadmap it is **not the next wave** — the altimeter (W0) comes first, and much of Wave 10's
value gets absorbed by the real bake/material subsystems (Phase 1) and the generalized UV
solver (Phase 2). Recommendation: **shelve the Wave 10 recipe**; if any part ships now, ship
it as an accelerator after the altimeter exists to prove it helps.

## 8. Risks

- **Altimeter is itself a judge** → calibrate with score anchors + reference; keep objective
  gates as the un-gameable floor so the judge only arbitrates the taste delta above the floor.
- **Generalization may underperform recipes on common classes** → keep recipes available as
  optional priors; the DoD requires generalization to *pass*, not to *beat* every recipe.
- **Real bake/materials are large** → they are the quality ceiling; the baseline map (W0.3)
  confirms they're the top blockers before committing the spend.
