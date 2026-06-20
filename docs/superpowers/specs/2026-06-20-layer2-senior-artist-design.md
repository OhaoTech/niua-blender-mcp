# Design — Layer 2: The Senior Artist (scaffold + convergence loop)

**Date:** 2026-06-20
**Status:** Approved (design)
**Depends on:** Layer 1 (complete capability surface) — DONE (manifest, `capabilities.*`, 302 tests).
**Scope:** The scaffold that lets an agent reach senior-technical-artist *output quality*, plus the long-term convergence loop that grows that quality. Standalone; zero niua knowledge.

---

## 1. The bar and the bet

**Bar:** output that competes with ~30 years of senior technical-artist expertise.
**Bet:** we do not hand-author all that expertise. We hand-build a *scaffold* + a few
seeded recipes, then a **budget-bounded convergence loop** grows the rest by
attempting a fixed **senior task battery** and converging against a trustworthy
**quality signal**. ("Forward modeling is the bet.")

Two phases:
- **Phase A — the scaffold (deterministic engineering, like Layer 1).** Eyes,
  objective metrics, the battery + harness, the judge, the playbook/verb store +
  seeds. Built and unit-tested before any big autonomous spend.
- **Phase B — the convergence loop (the long-term workflow).** Uses Phase A to
  attempt → observe → judge → improve → distill, accreting playbooks + craft
  verbs until the battery passes (or budget/plateau). Budget-bounded, commits +
  reports at checkpoints, pauses before merge.

## 2. Decisions (locked in brainstorming 2026-06-20)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Knowledge source | **Hybrid: seed + grow.** Hand-build scaffold + seed canonical playbooks/verbs; the loop extends/refines them. |
| 2 | Battery scope | **All four competencies:** modeling+topology, UV unwrap+packing, normal bake high→low, materials+rig. |
| 3 | Quality signal | **Objective gates + rubric LLM-judge**, judge run as an **adversarial multi-lens panel** to resist gaming. Pass = gates pass AND judge ≥ threshold. Self-contained (no reference corpus). |
| 4 | Governance | **Budget-bounded + checkpoints.** Commit + report at each checkpoint; pause before merge to main. Stop on: battery passes, OR token budget exhausted, OR plateau (K rounds no gain). |

## 3. The quality signal (the most important thing)

For an autonomous loop, **the scoring function IS the product.** If it is gameable
the loop finds the exploit, not mastery. Two channels, combined:

- **Objective gates (un-gameable, deterministic, computed in Blender).** Per
  competency, hard thresholds the artifact must meet:
  - *topology:* `quad_ratio ≥ T`, `ngon_count == 0`, `non_manifold_edges == 0`,
    `pole_count ≤ T`, `tris within budget`.
  - *uv:* `texel_density within ±T% of target`, `overlap_area ≈ 0`,
    `packing_efficiency ≥ T`, `stretch ≤ T`.
  - *bake:* `normal_map_error ≤ T`, `silhouette_delta ≤ T`, `cage fit ok`.
- **Rubric judge (carries the subjective competencies).** A multimodal agent is
  fed the multi-angle renders + the **eye-overlays** (topology/UV/shading/silhouette)
  + a **written senior rubric** per task, and returns a 0–10 score + critique.
  Run as an **adversarial panel** of N judges with *distinct lenses* (e.g.
  correctness / craft-convention / does-it-read-as-senior); a finding/score
  survives only on majority. Default-skeptical prompts.

**Pass = all objective gates pass AND median panel score ≥ threshold.** The gates
prevent the judge from being talked into garbage; the judge prevents
metric-gaming that looks wrong.

## 4. Phase A — the scaffold

### 4.1 Deeper eyes (perception)
New read-only captures, same graceful-degrade contract as today's `feedback.*`
(`available: false` headless/no-GPU), same dedicated hidden capture camera, same
two-channel return (images + analytic). Built on the existing `core/capture.py`
framing engine.
- **Topology overlay** — wireframe + highlighted n-gons/tris, poles (valence≠4),
  non-manifold edges. (Also verify/fix the known WIREFRAME-renders-as-solid issue
  in `core/capture.py::_configure_engine`.)
- **UV render** — islands in UV space + a checker map applied in 3D (texel density
  made visible).
- **Shading-error render** — face orientation (red backfaces) + normal artifacts.
- **Silhouette render** — flat matte from N angles (form/proportion read).
- **Lookdev render** — studio-lit turntable for materials (EEVEE + a neutral
  studio light/world).

### 4.2 Objective metrics
Extend `feedback.quality` (today: topology/symmetry/proportion/scale) with:
- **uv block:** `texel_density`, `overlap_area`, `packing_efficiency`, `stretch`.
- **bake block** (produced by the bake verb): `normal_map_error`,
  `silhouette_delta`, `cage_ok`.

### 4.3 Senior task battery + harness + judge (`evals/`)
- `evals/battery/<task>/` — each task = `task.json` (id, competency, setup recipe,
  objective gates with thresholds) + `rubric.md` (the written senior rubric for
  the judge). Standalone, in-repo.
- **Harness** (`evals/harness.py`) — given a task and an *artifact-producer*
  callable, runs setup → producer → scoring → returns a **scorecard**
  (`{task, gates: {name: {value, threshold, pass}}, gates_pass: bool,
  judge_score, judge_pass, pass, trajectory}`).
- **Gate checker** (`evals/gates.py`) — deterministic; reads metrics from
  `feedback.quality` (+ bake block) and evaluates each threshold.
- **Judge interface** (`evals/judge.py`) — a stable contract
  `judge(images, overlays, rubric) -> {score, critique}` with a deterministic
  **stub** for Phase A unit tests; the real multimodal panel is wired in Phase B
  (it is an *agent*, not deterministic code).

### 4.4 Playbook + craft-verb store (the *growing* Layer 2)
- `playbooks/<competency>.md` — recipes + heuristics the agent reads, **seeded**
  with canonical entries; a loader (`playbooks/__init__.py: load_playbook(name)`)
  the workflow injects into agent prompts.
- **Seed craft verbs** (tier-1 composite tools, server SPECS + addon handlers,
  parity-checked like all tools): `model.retopo_quads`,
  `uv.smart_unwrap_and_pack`, `bake.normals_high_to_low`, `shading.author_pbr`.

### 4.5 Phase-A delivery strategy: vertical slice first
The first Phase-A plan builds the scaffold **proven end-to-end on ONE competency
(modeling+topology)** — topology eye, gate checker, the modeling battery task,
the harness, the judge interface+stub, the playbook store + retopo seed. This
proves the whole pipeline before breadth. **Wave 2** (a follow-on plan) replicates
the proven pattern for UV, bake, and materials+rig (their eyes, metrics, tasks,
seed verbs). Rationale: a working vertical slice de-risks the big Phase-B spend.

## 5. Phase B — the convergence loop (the long-term workflow)

A `Workflow` script (`workflows/converge.js`-style, run via the Workflow tool).
Per battery task, a pipeline:

```
attempt   → an agent drives Layer-1 tools + current playbooks/verbs toward the task goal
observe   → eyes (overlays + multi-angle) + feedback.quality metrics
judge     → gate checker (deterministic) + adversarial rubric-judge panel
  ├─ fail → critique distilled → improve attempt → repeat (track trajectory)
  └─ pass → distill what worked into a playbook entry (+ propose a craft verb)
            → commit + checkpoint report → pause for approval before merge
```

- **Governance:** budget-bounded (`budget.remaining()` guard); plateau detection
  (K rounds no objective-gate gain → stop that task); commit + report each
  checkpoint; never auto-merge to main.
- **Parallelism:** the four tasks fan out; the judge panel is the verify stage;
  distillation is synthesis. (Wave-1 runs the one proven task; wave-2 adds three.)
- **Growth artifact:** every pass appends to `playbooks/` (and optionally emits a
  craft-verb spec for human review) — this is Layer 2 accreting, version-controlled.

`★ The loop only converges if the gates are real.` Phase A's gate checker +
overlay eyes are what make Phase B trustworthy; that is why they are built and
unit-tested first.

## 6. Non-goals / deferred

- Wave-2 breadth (UV/bake/materials eyes+tasks+verbs) — same pattern, separate plan.
- Reference-corpus grounding — not used (decision 3: self-contained).
- Game pipeline (LOD/collision/atlas/engine conventions) — later, separate.
- The real multimodal judge panel is a Phase-B *agent*, not Phase-A code (Phase A
  ships the interface + a deterministic stub so the harness is unit-testable).

## 7. Success criteria

- **Scaffold (Phase A):** topology eye renders a correct overlay (n-gons/poles/
  non-manifold visibly marked); `feedback.quality` gate checker evaluates the
  modeling task's thresholds; the harness runs the modeling task end-to-end with
  the judge stub and returns a well-formed scorecard; retopo playbook loads;
  all unit tests green; one manual battery run on a deficient mesh shows the
  scorecard transitioning fail→pass as the mesh is fixed.
- **Loop (Phase B):** starting from Layer-1-only, the loop drives the modeling
  task from fail to pass, and the trajectory + a distilled playbook entry are
  committed at the checkpoint. Extends to all four tasks in wave 2.

## 8. Risks & mitigations

- **Gameable judge** → objective gates always required; adversarial multi-lens
  panel; default-skeptical prompts; gates cap the judge.
- **Bad eyes mislead the loop** → unit-test overlays against known meshes
  (a cube has 8 valence-3 poles; an n-gon mesh shows n-gons) before Phase B.
- **Runaway cost** → budget guard + plateau detection + checkpoint pauses.
- **Distilled playbook drift** (loop learns a bad habit) → playbook changes are
  committed and human-reviewed at the checkpoint before merge; regression: every
  passed task is re-run after a playbook change.
