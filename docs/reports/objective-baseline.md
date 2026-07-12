# Objective Baseline — Readiness + Preservation (the new primary grade)

**Date:** 2026-07-03 · **Runner:** `scripts/run_objective_benchmark.py --mode baseline` (deterministic, NO LLM judge).
**Note:** `baseline` mode is a no-op finisher = an INPUT-QUALITY probe of the raw intake meshes (grade `INVALID`
by design — it does not run a finisher). It exists to validate the ruler live + record the intake readiness floor.

## The ruler works live (first validation)
- `feedback.capture_intake` renders 3 alpha ortho silhouette masks live; `feedback.readiness` scores objective
  gates order-free; `feedback.preservation` self-IoU = **exactly 1.0** on an unchanged mesh (deterministic, no AA
  noise — the "SEM≈0" the audit demanded), and drops + flags `bbox_delta.changed` on a deliberate form change.

## Baseline readings (raw intake, per class)
| class | mean_readiness (gates passed) | mean_preservation |
|---|---|---|
| hard_surface_prop | 0.52 | 1.0 |
| from_scratch_prop | 0.48 | 1.0 |
| generated_cleanup | 0.48 | 1.0 |
| organic_prop | 0.42 | 1.0 |

Per item readiness: barrel .48 · blob .52 · shell .44 · bracket .48 · crate .56 · pumpkin .40 · rock .44.
(preservation = 1.0 trivially — baseline is a no-op; the real preservation signal appears once a finisher runs.)

## Follow-ups RESOLVED (2026-07-03)
- All 7 items now measure preservation (fixed 2 recipes that produced degenerate meshes when run mechanically).
- Runner is DETERMINISTIC: two full runs byte-identical (per-item scene-reset via `object.delete`).
- Per-item readiness: barrel .48 blob .52 shell .52 bracket .48 crate .56 pumpkin .48 rock .44 (mean ~0.50); preservation 1.0 (no-op baseline).

## (Historical) known follow-ups
1. **Preservation render robustness:** 2/7 items (`generated_shell` = open mesh; `organic_pumpkin` = left in EDIT
   mode by its recipe) return preservation UNMEASURED (fail-closed → excluded from means, NOT falsely 1.0).
   Fix: `capture_intake` should force OBJECT mode + handle open meshes / non-separable alpha.
2. **Runner scene-reset:** the runner accumulates `bench_*` objects across runs; reset/clear the scene per run
   for clean run-to-run determinism (the metric itself is deterministic — verified by the exact-1.0 self-IoU).

The judged altimeter is demoted (non-primary). This objective bench is the primary grade every future deletion
is validated against.

## Post-deletion confirmation (2026-07-10, lean-rebuild Phases 3-4)
After deleting the pipeline FSM + craft/knowledge/verbs/prose (~2,900 lines), the real-asset baseline is byte-identical: 0.36/0.36/0.36/0.24/0.28, preservation 1.0, 5/5 measured. First agent-mode run (deterministic finisher): mean readiness 0.32 -> 0.72, zero harm flags, godot import 5/5 clean — see docs/reports/agent-finisher-first-run.md.

## Post two-layer-split confirmation (2026-07-10)
After reorganizing into interface/ vs finishing/ layers (commits e512b58..c106a91, boundary enforced by tests/test_layer_boundary.py): baseline byte-identical again — 0.36/0.36/0.36/0.24/0.28, preservation 1.0, 5/5 measured.

## Post product-hardening confirmation (2026-07-10)
After the hardening block (timeout tiers, system.health, op table + progress/cancel + sideband, supervisor, capabilities.tools, teaching errors, spec-lint, turns metric, session log + report — commits a562835..50adf80): baseline items/reading byte-identical — 0.36/0.36/0.36/0.24/0.28, preservation 1.0, 5/5. LIVE: supervisor self-heal verified (kill -> bridge back in ~14s); system.health + sideband system.operations answering live.

## Post code-mode-substrate confirmation (2026-07-12)
Finisher ported to the make_game_ready SKILL over the generated tool-client SDK; evals/finisher.py delegates. Agent-mode benchmark byte-identical — 0.76/0.80/0.80/0.60/0.64, 0 harm. Code-mode token win: per-asset 1.5-2.3x (pessimistic), per-session amortized 7.6x and up — mechanism proven: 16-25k tokens of intermediates per asset collapse to a 0-35 token summary. See docs/reports/code-mode-token-win.md.
