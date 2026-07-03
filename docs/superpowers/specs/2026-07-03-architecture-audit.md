# Bottom-to-Top Architecture Verdict + Lean Rebuild Plan

**Date:** 2026-07-03
**Author:** Architecture synthesis (resolves 2 inventories + 5 audit lenses against this session's hard evidence)
**Product identity:** A standalone agentic Blender MCP that is a **technical finisher** — it takes generated/raw 3D form and makes it **game-ready** (repair, retopo, UV, bake, material, LOD, collision, export to Godot). It does **not** author form. The operator is Claude driving Blender via MCP; a human watches the visible viewport.

---

## 0. The verdict in one paragraph

**The foundation is genuinely solid. The superstructure is inverted.** Layer 1 (kernel, bridge, dispatch, parity, the perception eyes, objective quality metrics, checkpoint/revert) maps almost 1:1 onto the minimal correct architecture and is well-tested — keep essentially all of it. The Layer-2 superstructure is built on one wrong premise: that the agent is a *knowledge-poor executor* who must be marched through a fixed pipeline, taught the targets, handed the recipes, and quoted the manual. The operator is a *knowledge-rich, perception-equipped* agent that already holds all of that. So most of Layer 2 is either **frozen re-statement of what the agent knows** (knowledge packs, craft recipes, asset-class prose) or a **control cage that has already drawn blood** (the FSM's auto-revert deadlock, the composite verbs' form damage). The one part of Layer 2 that is load-bearing — the **objective gate contract** and the **per-class numeric thresholds** — detaches cleanly from the machine wrapped around it and becomes the redesign's `readiness` axis. **Keep the numbers, keep the eyes, keep the safety net; delete the machine and the playbook; invert control so the agent drives against an order-free definition-of-done.**

---

## 1. The minimal correct architecture (first principles)

Ask the collapsing question: *the agent is Claude — what does it lack that only the machine can supply?* An intelligent agent already brings planning, sequencing, and the entire body of technical-artist knowledge. It categorically cannot supply four things, and those four things — plus the plumbing — are the **entire** system:

| Slot | Why only the machine can supply it | Component |
|---|---|---|
| **M1 — HANDS** | The agent cannot execute `bpy`; it needs a typed, undo-safe, main-thread hand where a hallucinated call fails cleanly. | Finishing capability surface (~30 verbs on the finishing path + a generic mesh-edit primitive) |
| **M2 — EYES** | The agent cannot see the viewport or eyeball non-manifold counts, UV stretch, or silhouette drift. | Multi-angle capture / silhouette / topology overlay **+ objective metrics** |
| **M3 — DONE** | The agent has no un-fudgeable ground truth for "game-ready"; left to taste it declares victory or chases a mirage. | **Two deterministic axes:** Readiness (fraction of technical gates passed) + Preservation (input↔output silhouette IoU) |
| **M4 — SAFE ITERATE** | The agent makes destructive mistakes and must hill-climb without ratcheting damage. | `session.checkpoint` / `revert` |
| **M5 — GLUE** | How M1 reaches Blender safely and M2 comes back. | MCP kernel / TCP bridge / main-thread dispatch / spec↔command parity |
| **M0 — CONTEXT** (prose, not a tool) | Everything the agent *reads* (the finishing order, the "preserve form, decline formless input" charter, the accept/revert loop) belongs in the prompt, not a queryable registry. | Identity + operating instructions in the agent's context window |

**That is the whole system: five tools and a paragraph.** No state machine, no class taxonomy, no recipe registry, no manual-in-a-tool, no LLM judge. The diagnostic that resolves every disagreement below: **tools exist only to give the agent truth it can't see, actions it can't take, and a done-line it can't move. If the agent already knows it, it goes in the prompt.** Every recurring failure this session traces to building a tool for the "agent already knows it" category.

---

## 2. Component-by-component verdict

Confidence = how sure the verdict is given the code + the session's hard evidence.

### Layer 1 — the believed-solid base

| Component | Verdict | One-line why | Confidence |
|---|---|---|---|
| MCP kernel (contract / router / validation) | **KEEP** | Clean, tier-precedence correct, 40+ tests; irreducible M5 glue. | High |
| TCP bridge + JSON-RPC server | **KEEP** | Robust framing, correct error classification, tested. | High |
| Addon bridge_server (main-thread queue) | **KEEP** | Queue+Event pattern correct; undo pushed *after* success. | High |
| Dispatch + SPECS↔COMMANDS parity | **KEEP** | Preconditions before mutation; parity test guards drift. | High |
| Context resolver (mode/select/area) | **KEEP** | Sound; one ordering assumption (mode restored before area exits) to verify vs Blender 5.1, non-blocking. | High |
| `session.checkpoint` / `revert` | **KEEP** | The M4 safety net; fresh-copy restore is correct. Minor: non-mesh datablocks silently null (low, out of scope for a finisher). | High |
| Perception eyes (capture / capture_views / silhouette / topology / turntable / local-view isolation) | **KEEP** | The crown jewel — the one thing nothing else can supply. | High |
| `feedback.quality` objective metrics | **KEEP + DECOUPLE** | Load-bearing M2/M3 floor. **But it imports `pipeline_store` and calls `get_state()` at `feedback.py:233`** — the solid base reaches up into the Layer-2 singleton. Pass `asset_class` explicitly instead. | High |
| `feedback.critique` (images + report bundle) | **KEEP** | The agent's main observe primitive; repurpose for preservation diff. | High |
| Codegen / generated specs (RNA) | **KEEP** | Auto-discovery + tier precedence; sound. | High |
| Layer-1 capability surface (312 specs / ~54 domains, full GUI parity) | **SIMPLIFY (narrative, not deletion)** | Load-bearing = the ~30 finishing verbs + generic mesh-edit. Rigging/animation/NLA/particles/grease-pencil are inert parity, not the spine. Harmless at runtime but they inflate scope and enlarge the agent's tool-choice surface. Keep them; stop treating "303 tools" as the product — consider lazy-cataloguing non-finishing domains. | Medium |

**Is the base actually solid? Yes.** Three known issues (context-restore ordering, non-mesh checkpoint, handler-exception normalization) are low/medium and *not architectural*. The **one** real architectural defect in the base is the `feedback.quality → pipeline_store` coupling leak — and fixing it is a prerequisite for safely deleting the FSM.

### Layer 2 — the superstructure under question

| Component | Verdict | One-line why | Confidence |
|---|---|---|---|
| **9-stage pipeline FSM — control surface** (`advance` as order-blocker, `gate_check`-as-gate, `rollback_pointer`, `current_stage`, `completed[]`/`terminal`, `_STORE` as progress truth) | **DELETE** | A conveyor belt is the right pattern for a *dumb* executor; here it duplicates the agent's own planning while providing none of the safety (safety lives in gates+checkpoint, both FSM-independent). Its monotonic-accumulation world-model **already deadlocked** the do-no-harm guard (retopo/LOD legitimately reduce geometry) — that is the structure telling the truth about itself. | High |
| **9-stage pipeline — the ledger inside it** (intake baseline / per-stage checkpoint labels) | **KEEP as a thin passive ledger** | The redesign genuinely needs somewhere to store intake silhouette masks and a checkpoint convention. That is a passive per-object scratchpad the agent reads/writes — **not** a forced-order machine. This is the keep-defender's one surviving structural point. | High |
| Per-stage **GATES** (`_GATES` + `check_gates` + `stage_gates`) | **KEEP + PROMOTE** | Deterministic, un-gameable, 100% passing, correctly modeled to engine constraints. This **is** the redesign's Readiness axis. Promote to an order-free `feedback.readiness` checklist; stop marching them single-file. | High |
| ASSET_CLASS — `gate_overrides` + budgets (tri/material/texture/LOD/collision) | **KEEP as a numeric contract** | These change deterministic pass/fail per input class (organic quads 0.85, scan 0.98); "objective done" is only correct *per class*, and per-class preservation floors need this as their key. Collapse the 4 near-duplicate profiles to base + sparse deltas. | High |
| ASSET_CLASS — taxonomy + hard default (`asset_class="hard_surface_prop"`) | **SIMPLIFY** | The class is a real key but is *frequently guessed* (`asset_class_defaulted` exists). Replace the static default with **perception-driven intake triage**: the agent looks at the mesh and sets the class (or declines formless input). A wrong default = a wrong contract. | High |
| ASSET_CLASS — `stage_targets` + `guidance` prose | **DELETE** | Restates numerically-enforced gates + senior-artist common sense the agent already emits. Frozen, lower-resolution, sometimes prescriptive where the agent should decide from perception. | High |
| CRAFT_WORKFLOW registry (`list`/`describe`/`recommend`, 3 entries) | **DELETE** | A 3-row `asset_class×stage → recipe` lookup masquerading as senior judgment; `recommend()` decides from a *class label*, not perception — the exact diagnosed mistake. Its `required_tools` point at the disproven composite verbs. Zero capability lost. | High |
| Composite craft verbs (`modeling_verbs.py`, 6 verbs) | **DELETE 5, SIMPLIFY ≤1** | Fixed-order, fixed-parameter macros with **no per-edit accept/revert** — the do-no-harm gap hard-coded. `recess_panels`/`panel_detail_pass` *invent* form (charter violation); `retopo_quads` games the quad gate without real edge flow. Empirically + mathematically disproven (barrel 6.6→4.5; regressed material_read). Already excised from live `advance()`; delete the surface. Keep at most one prose-free cleanup macro *only if telemetry shows repeated identical composition*. | High |
| KNOWLEDGE packs (`list`/`load`, 7 packs) | **DELETE** | Per-stage prose whose `targets` **already drifted stale** vs the real asset-class overrides (0.95 vs 0.98/0.85) — a confirmed second source of truth. Standards/recommendations spoon-feed a senior; `sources` are manual *titles* with no text. If a gate-path→hint map is ever wanted it's a 20-line dict built against a measured need, not a domain + 2 tools + parity + tests. | Medium-High |
| EVAL — objective gates + scorecard gate-floor algebra | **KEEP** | The gate-floor (judges can't lift a gate-failing asset) is correct and load-bearing; reused wholesale as Readiness. | High |
| EVAL — benchmark items (7 held-out, 4 classes) | **KEEP (rescore on objective axes)** | The immune system that **caught** the form-craft damage. Delete this and you lose the only thing that empirically disproved a double-red-teamed build. | High |
| EVAL — altimeter 5-lens LLM judge + `form_critique`-as-grade + lens scorecard | **DELETE as primary (demote to labeled offline A/B diagnostic; cut if it re-tempts)** | SEM ≈ 0.73, blind below ~1.5 pts; measured the *wrong tool* (absolute form on a finisher); issued a **false build mandate** that produced real damage. A retained "diagnostic" is a standing temptation to taste-chase — keep only if firewalled from every roadmap decision. | High |
| PLANNED redesign — silhouette IoU metric, `feedback.preservation`, `feedback.readiness`, objective benchmark runner | **BUILD (this is M3) — but order-free, not FSM-bound** | Pure Python, deterministic, ~10× cheaper, red-team-corrected. Correct direction. Adjust: `readiness` aggregates all gate groups in *no order*; preservation masks live in the thin ledger + generic `session` checkpoints, not the FSM. | High |
| PLANNED redesign — do-no-harm guard | **BUILD as an agent-loop flag, not an `advance`-internal auto-revert** | Auto-revert inside `advance` is exactly what deadlocked. The per-stage-budget table is an FSM-rigidity workaround (a linear model has no concept of "reducing-but-valid"). In an agent loop there is no such contradiction: checkpoint → act → re-measure readiness+preservation → keep-iff-better, else revert. Flag on the objective diff; no stage-indexed exception table. | High |

### Absent-but-needed — ADD

| Addition | Verdict | Why | Confidence |
|---|---|---|---|
| **Godot round-trip import verification** (via the `niua-godot` MCP) as the apex Readiness gate | **ADD** | Identity is "game-ready in Godot." The strongest done-signal is not a Blender-side `export_profile` proxy — it is: does the exported glTF import clean into headless Godot (no errors, correct scale/axis, materials resolve)? Converts "done" from proxy into ground truth. The one genuinely missing load-bearing component, and you already have the MCP. | High |
| **Perception-driven intake triage** ("is this finishable? which class?") | **ADD (thin)** | Sets the numeric contract from what the agent *sees*, and lets the tool decline formless input (the blob) back to the generator instead of heroically smoothing noise into a smooth nothing. | Medium-High |
| **Name the per-edit accept/revert loop in M0 context** | **ADD (prose)** | Not a new component — its ingredients (eyes + checkpoint + metrics) exist — but naming it as THE core control law is what turns blunt verbs into a monotone hill-climb that cannot score below its start. | High |

---

## 3. Adjudicating the minimalist ⟷ keep-defender disagreement

The two lenses collide on exactly one thing: **the pipeline state machine.** Everything else they converge on (keep gates, keep asset-class *numbers*, keep benchmark, delete verbs, demote judge). So the whole debate reduces to: *is the FSM the spine the redesign bolts onto, or a cage to delete?*

**Keep-defender's strongest cards, and how each falls:**

1. *"`advance()` fuses enforced-observation + objective gate + auto-checkpoint — delete it and you lose all three."* — The three separate cleanly. Enforced observation is a **norm** the eval harness enforces ("run readiness before export"), not a 9-node FSM. The objective gate is `check_gates`, which is stateless and order-free. The auto-checkpoint is generic `session.checkpoint` with a label convention — it does not need `current_stage`. You lose the *fusion*, which is precisely the rigidity, not the value.

2. *"The redesign bolts onto the stages — preservation masks live in pipeline run-state, the guard fires inside `advance`, budgets are stage-indexed."* — This conflates "we need per-object run-state + a checkpoint convention" (**true** — kept as the thin ledger) with "we need a forced-order machine" (**false**). The guard firing "inside `advance`" is the very thing that **deadlocked** (hard evidence). Stage-indexed budgets exist *only* to patch the FSM's inability to express "reducing-but-valid" — an agent loop measuring the objective diff needs no such table.

3. *"The FSM is the human-watchable map."* — Per-group readiness ("retopo 3/3, uv 2/4, bake 0/2") is a *richer* live status than a single `current_stage` pointer, and the agent narrates its own plan. Concede the value; reject the mechanism.

4. *"It's a real dependency DAG."* — Correct, and that is why the FSM is unnecessary: **the dependencies are already encoded in the gates as failures.** Bake fails with no UVs; export fails with unapplied transforms. Ordering enforced by the *target* is flexible; ordering enforced by a *pointer* is brittle and freezes one canonical line over a real DAG.

**The decisive tie-breaker is the session's own base rate.** Every top-down rigid structure built from the senior-artist mental model has broken against reality *after* the bill was paid: form verbs damaged good inputs, the auto-revert guard deadlocked, the judge was noise. The keep-defender's essential claim is "but *this* rigid structure hasn't been disproven yet." Given that (a) the FSM's core assumption *already* drew blood via the guard deadlock, and (b) its one valuable organ (the gates) detaches with zero loss, the burden of proof is on keeping it, and it isn't met.

**Where the keep-defender is right and the minimalist over-reaches:** the redesign *does* need a place to store intake masks and something to revert to. The minimalist's "delete Layer 2, let the agent freestyle" would throw that away. The resolution is not "delete everything" — it is **delete the control machine down to a thin passive ledger.** That is the synthesis both lenses can live with, and it is the verdict.

**Ruling:** DELETE `advance`/`gate_check`-as-blocker/`rollback_pointer`/`current_stage`/`completed`/`terminal`/`_STORE`-as-progress-truth. KEEP a thin per-object ledger (intake masks + checkpoint labels). PROMOTE gates to order-free `feedback.readiness`. This is the pipeline-skeptic's position, refined by conceding the keep-defender's ledger.

---

## 4. The lean target architecture

```
M0  CONTEXT (prose, in the prompt) ─ absorbs knowledge packs, craft recipes, asset-class guidance
      identity: "You are a technical finisher. Preserve inherited form. Decline formless input."
      the standard finishing order (as guidance, not a gate) + the per-edit accept/revert loop

TOOLS
  M1  HANDS      finishing verbs (repair, retopo, uv, bake, material, LOD, collision,
                 transform-apply, export) + generic mesh-edit          [prune 312 → the finishing path]
  M2  EYES       capture / capture_views / silhouette / topology / quality-metrics   [keep as-is]
  M3  DONE       feedback.readiness    — order-free gate checklist, per-class, + Godot import  [promote gates]
                 feedback.preservation — input↔output silhouette IoU (min across angles)        [build]
  M4  ITERATE    session.checkpoint / revert                            [keep as-is]
  M5  GLUE       kernel / bridge / dispatch / parity                    [keep as-is]
  LEDGER         intake baseline masks + checkpoint labels (passive per-object scratchpad)  [thin]

NUMERIC CONTRACT (one config beside the gates)
  per-class budgets (tri/material/texture/LOD/collision) + gate_overrides (quad/stretch)

DELETED
  pipeline FSM control (advance/gate_check-blocker/rollback_pointer/current_stage/completed/terminal)
  craft_workflow registry + 5 composite form verbs (disproven, charter-violating)
  knowledge packs (redundant + already stale)
  asset-class prose (stage_targets/guidance)
  altimeter 5-lens judge as any steering signal

ADDED
  Godot round-trip import gate (apex of Readiness)
  perception-driven intake triage (sets class / declines formless input)
```

Nothing load-bearing is cut: the agent still can't see (M2), act (M1), fudge done (M3), or safely iterate (M4). Every deletion is either knowledge returned to context where it's higher-resolution and trivially edited, or a control structure empirically shown to deadlock or damage. **Net surface change: ~11 Layer-2 tools removed, 0 capability lost, ~10× cheaper eval, and the base decoupled from the superstructure.**

---

## 5. The rebuild / migration plan (safe, reversible, incremental)

Guiding safety rule: **build the ruler before you strip anything, so every deletion is validated by "the objective benchmark number is unchanged."** 774 tests protect the base; the objective bench protects the outcome. Each phase is its own branch/PR, reversible, and gated behind green parity + surviving unit tests + green objective bench. Never delete a module while another reads it.

**Phase 0 — Decouple the base (no behavior change, unblocks everything).**
Fix the `feedback.quality → pipeline_store.get_state()` leak (`feedback.py:233`): pass `asset_class` as an explicit argument instead of fishing it out of the FSM singleton. This is a prerequisite for deleting the FSM and de-risks it. Fully reversible; all existing tests must stay green. *~half a day.*

**Phase 1 — Build the ruler FIRST (pure addition, 774 tests stay green).**
Implement the locked eval-readiness-preservation plan (Tasks 1/2/4/5) **but order-free**: `feedback.readiness` aggregates all gate groups in no order; preservation masks store in the thin ledger + generic `session` checkpoints; the do-no-harm guard is an **agent-loop flag on the objective diff**, not an `advance`-internal auto-revert (Task 3 rewritten — drop the per-stage-budget table). Rescore the 7 benchmark items on readiness + preservation. No deletion yet. *~1 week.*

**Phase 2 — Characterize + baseline + demote the judge.**
Run the objective bench N≥2, confirm SEM ≈ 0 (deterministic), record a trusted baseline. Add it as the CI/PR gate. Relabel `altimeter.mjs` non-primary (banner + `meta`); mark `altimeter-baseline.md` historical. *~1–2 days.*

**Phase 3 — Strangle the FSM (each deletion behind green bench).**
Migrate the ledger (intake masks + checkpoint labels) off `_STORE`-as-progress into a passive run-state object. Then delete `advance`/`gate_check`-as-blocker/`rollback_pointer`/`current_stage`/`completed`/`terminal` and the ordered pipeline domain tools, plus their tests. Keep `stage_gates`/`check_gates`/`asset_classes`. Confirm objective bench unchanged after each delete. *~3–4 days.*

**Phase 4 — Strip the scaffolding (one reversible commit per module).**
Delete: `craft_workflow` registry + 5 composite verbs (`modeling_verbs.py`) + the `knowledge` domain + asset-class prose fields. Collapse the 4 asset-class profiles to base + sparse deltas. Delete their test files (`test_craft_workflow.py`, etc.). Each behind green parity + green bench. *~2–3 days.*

**Phase 5 — Add the apex + intake triage.**
Wire the Godot round-trip import check (export → headless Godot import via `niua-godot` MCP → assert no errors / correct scale-axis / materials resolve) as the top Readiness gate. Add perception-driven intake triage that sets the class and declines formless input. Update M0 context prose (charter + finishing order + accept/revert loop; absorb the deleted knowledge/recipes/guidance). *~1 week.*

**Rollback story at every step:** phases are additive-then-subtractive; the subtractive phases (3–4) are pure deletions behind a deterministic bench and a full unit suite, so any regression is a one-commit revert. The base (Phases keep it untouched except the decouple) never loses test coverage.

---

## 6. Process change to prevent recurrence

The recurrence has one root cause (process-efficiency lens, fully adopted): the team ran **design → build → harden → (much later) measure**, so *rigor was spent proving the code matched the design instead of proving the design matched reality.* 774 green tests are fully consistent with a tool that lowers a 6.6 to a 4.5, because none of them measure the outcome. The fix is to invert the order and shrink the batch:

- **Ruler first.** Build the cheapest objective outcome metric *before* any structure it would grade — then characterize its noise (N≥2, report SEM) *before* reading it. The eval-redesign discovered this by accident; make it the standing rule.
- **Tracer-bullet unit, not "Wave."** The unit of work is *the smallest change that can move the ruler beyond noise*, not a subsystem. The form-craft premise was a one-verb, one-measurement experiment (build `smooth`, run on the barrel, watch 6.6→4.5, kill it in an afternoon) — instead it became a red-teamed wave.
- **Measure the premise before you harden it.** A cheap measurement is a cheaper falsifier than a red-team round and tests the *right* thing (external validity). Red-team only premises that survived a measurement; red-teaming a doomed premise manufactures false confidence.
- **No structure without a measured caller.** Don't build asset-class overrides until a measurement proves two classes need different thresholds; don't build a knowledge pack until an agent measurably fails without it. Structure is *pulled* by evidence, never *pushed* by the mental model.
- **Redefine "done."** Ship-readiness = benchmark delta past noise, never green CI. Keep the 774 tests — they protect the base — but never let them stand in for an outcome measurement.
- **The one-line design test:** before building any Layer-2 structure ask *"does the agent already know this, or can only the machine supply it?"* If the agent knows it, it goes in the prompt.

---

## 7. Decision points for the founder

1. **The FSM (the load-bearing call).** Adopt the ruling — **delete the pipeline's control surface down to a thin passive ledger, and let the agent drive freely against an order-free `readiness` + `preservation` definition-of-done?** Recommendation: **yes.** Its one valuable organ (the gates) detaches cleanly; its core assumption already deadlocked the guard; keeping it doubles the definition-of-done into two divergent sources. This is the single most important structural change.

2. **Knowledge packs + asset-class taxonomy: numbers-only now, or keep the gate→remediation prose?** Recommendation: **delete to numbers now.** The packs already drifted stale vs the real overrides (concrete harm), and an Opus-class agent reading `quad_ratio actual=0.7 required>=0.95` already knows to retopo. If a gate-path→hint map ever proves needed, rebuild it as a 20-line dict against a *measured* gap — not a domain.

3. **The definition of "done": stop at Blender-side gates, or invest now in Godot round-trip import as the real done-gate?** Recommendation: **invest now.** The identity is "game-ready in Godot," you already have the `niua-godot` MCP, and it converts the apex of Readiness from a proxy into ground truth. This is the one genuinely missing load-bearing component.

(Implicit 4th, low-stakes: keep `altimeter.mjs` as a firewalled offline A/B diagnostic, or cut it? Recommendation: demote now, spend nothing more on it, cut it the first time it re-tempts a roadmap decision.)
