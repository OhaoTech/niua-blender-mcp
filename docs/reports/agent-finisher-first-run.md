# First real finishing run — deterministic finisher on real generator assets

**Date:** 2026-07-10 · **Branch:** lean-rebuild · **Runner:** `scripts/run_objective_benchmark.py` (deterministic, judge-free) · **Finisher:** `niua_blender_mcp.evals.finisher:finish` (gate-driven, per-move checkpoint → act → re-measure → keep-or-revert)

## 1. Post-deletion baseline: bench unchanged ✅

After deleting the pipeline FSM control surface, craft_workflow, knowledge packs, composite form verbs, playbooks, and asset-class prose (Phases 3–4, ~2,900 lines removed), the baseline reading is **byte-identical** to the pre-deletion baseline:

| item | readiness | preservation |
|---|---|---|
| real_character | 0.36 | 1.0 |
| real_character_light | 0.36 | 1.0 |
| real_creature | 0.36 | 1.0 |
| real_multipart | 0.24 | 1.0 |
| real_prop | 0.28 | 1.0 |

mean_readiness 0.32 · 5/5 measured · valid. Every deletion is validated by the ledger rule ("objective bench unchanged").

## 2. Godot round-trip axis, baseline mode

New apex axis (export → `godot --headless --import` on a throwaway project → assert clean): **5/5 raw intakes already import clean** into Godot 4.6.3. The raw generator output is import-valid; the axis exists to catch what a finishing pass (or a malformed asset) breaks.

## 3. Agent mode — the first honest finishing reading

| item | readiness before → after | preservation | harm | godot |
|---|---|---|---|---|
| real_character | 0.36 → **0.76** | 0.926 | none | clean |
| real_character_light | 0.36 → **0.80** | 0.997 | none | clean |
| real_creature | 0.36 → **0.80** | 0.987 | none | clean |
| real_multipart | 0.24 → **0.60** | 0.991 | none | clean |
| real_prop (978k tris) | 0.28 → **0.64** | 0.895 | none | clean |

**mean_readiness 0.32 → 0.72 (+0.40)** · mean_preservation 0.959 (floor 0.85) · n_harm_flagged 0 · godot 5/5 clean · 5/5 measured · valid.

### The accept/revert loop fired for real

`real_character`'s `decimate_to_budget` move dropped silhouette preservation to **0.793 (below the 0.85 floor) → automatically REVERTED**; the item still climbed 0.36 → 0.76 through its other moves. This is the do-no-harm control law working exactly as designed — measured harm rejected, progress preserved. Every other move (39/40) was kept on merit: readiness non-decreasing AND preservation above floor.

Moves that reliably moved the needle: `pbr_maps` (+0.12–0.16 everywhere), `lod` (+0.08–0.12), `collision` (+0.08–0.12), `decimate_to_budget` (+0.04 where kept). `repair`/`tris_to_quads`/`uv_unwrap` mostly held readiness flat — see gaps below.

## 4. Next gaps (this list IS the roadmap)

Live failing gates on the finished `bench_real_prop` (readiness 0.64), representative of the remaining gap across items:

1. **Density**: `engine.within_triangle_budget` still False — the finisher's single decimate pass has a 0.01 ratio floor; a 978k-tri mesh lands at ~9.7k > 5000 budget. Needs iterative decimation (or a real retopo verb).
2. **Topology**: `topology.quad_ratio` 0.076 (need ≥0.95) and `topology.non_manifold_edges` 20,209 — `tris_to_quads` + `remove_doubles` are far too weak for dense generator meshes; this is the retopo/repair frontier.
3. **UV quality**: `uv.overlap_detected` True, `uv.stretch_ratio` 27.7 (need ≤2.0) — `smart_unwrap` at this density produces junk islands; UV work must happen AFTER density reduction, and the finisher's fixed move order can't revisit UV post-decimate (an agent driving the same tools can).
4. **Materials**: `textures_within_size` / `atlas_ready` False — imported 4k textures need resize/atlas verbs; no move exists for this yet.
5. **LOD chain**: `lod_triangle_reduction_ok` False — LOD1 at ratio 0.5 of an over-budget mesh is itself over the reduction target.
6. `real_character`'s reverted decimate shows organic dense meshes need silhouette-aware reduction (decimate-with-preservation-feedback loop, stepping ratio until the floor binds), not one fixed-ratio shot.

None of these are eval gaps — the ruler measured all of them honestly. They are HANDS gaps (missing/weak verbs) and SEQUENCING gaps (fixed order vs. agent-driven iteration), exactly what this deterministic reference finisher exists to surface.

Three harness-robustness gaps surfaced by the final whole-branch review (not scoring gaps — runner/process hygiene):

7. **Godot subprocess env not isolated**: the headless Godot round-trip inherits the user's editor settings (full environment passthrough) instead of a clean/minimal env; isolating `HOME` needs a writable editor-data dir for Godot to write its config into, which the runner doesn't provision yet — revisit for CI portability, where the current user's Godot config won't exist.
8. **Godot ERROR-line filter is too broad**: `evals/godot_roundtrip.py`'s import-failure detection counts any stderr `ERROR` line as a measured failure, which on some hosts includes benign host noise (audio backend / XDG warnings) unrelated to the import itself — tighten the filter to asset/import-related lines specifically when it first bites on a real host.
9. **Finisher checkpoints accumulate per item**: `session.checkpoint` in `evals/finisher.py` can fire up to 8 times per item (one per move), each snapshotting a datablock copy of the subject mesh — for a ~1M-tri real generator mesh that's up to 8 heavy copies retained per item. Fine at the current 5-item benchmark scale; needs explicit freeing (drop superseded checkpoints once a move is KEPT, not just on revert) before scaling to a larger item set.

## 5. Integrity notes

- Deterministic and honest: no LLM anywhere in the loop; unmeasured ≠ failed throughout; preservation fail-closed.
- The 978k-tri prop completed the full 8-move pass within per-call timeouts (the O(n²)→O(n) UV-overlap fix from fe88a19 is what makes repeated readiness reads on dense meshes affordable).
- Stray helper objects from reverted moves are cleaned (scene-diff + delete before revert).
