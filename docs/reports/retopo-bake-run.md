# Retopo-to-budget — live run (3 iterations, honest state)

**Date:** 2026-07-13 · **Branch:** retopo-to-budget · **Skill:** bake_and_finish with best-of-both reducer.
Verified three ways per asset: triangle budget (actual count), surface_fidelity, and a rendered look.

## What the loop fixed (verified)

1. **Reducer reliability.** `object.retopo` (voxel-remesh → quadriflow) silently missed budget — quadriflow cancels at aggressive targets and left the samurai 12× over (61k vs 5k), which a high fidelity number *hid*. Fixed: a decimate-collapse on the clean voxel mesh now guarantees the budget (samurai lands at exactly 18000, non-manifold 0).
2. **Budgets were wrong.** All 5 fixtures are characters filed under prop budgets. A samurai at 5000 tris is a blob (fidelity 0.568); added a `character` class (18000) and reclassified — the samurai now hits 0.688 and looks game-ready.
3. **Reducer routing.** Retopo helps bulky/hard-surface meshes but *lumps up* organic figures with thin features. Best-of-both (retopo-bake, then decimate-bake fallback gated on the budget) lets the fidelity ruler pick per asset — no heuristic.

## Per-asset result (18k character budget, best-of-both)

| asset | winner | fidelity | at budget | verdict |
|---|---|---|---|---|
| real_prop (samurai) | retopo | **0.688** | 18000 ✓ | **game-ready, looks right** ✓ |
| real_character_light | retopo | **0.901** | ✓ | ✓ |
| real_creature | decimate | **0.928** | ✓ | ✓ (retopo would have lumped it; loop chose decimate) |
| real_character | both fail | 0.577 / 0.275 | — | **surface noise** — voxel lumps the slim figure; decimate makes junk topology |
| real_multipart | — | — | — | **crashes Blender** (segfault in voxel/quadriflow on the 10-part mesh) |

So **3/5 are genuinely game-ready** at correct budgets, verified by eye — including the samurai that started "this is garbage." Two remain hard.

## The two hard cases (honest root causes)

- **real_character — surface noise.** Rendered, the retopo'd figure is covered in lumpy barnacle-like artifacts (min-view SSIM 0.49). The voxel grid is too coarse/blocky for a slim, curved body; decimate on the raw organic mesh gives junk topology (0.275). Neither current reducer produces a clean surface here. Likely needs a finer voxel + a smoothing/shrinkwrap pass, working quadriflow quads, or a higher budget — real technique, not a floor tweak.
- **real_multipart — hard crash.** voxel/quadriflow segfaults Blender on the 10-part joined mesh (a C-level crash Python can't catch). The self-healing supervisor recovers Blender, but the run dies mid-item. Needs either the reducer to pre-guard/skip risky input, decimate-only for such meshes, or a crash-resilient runner that waits for supervisor recovery and falls back.

## Remaining for true "AAA / all features" (not yet done)

Even the 3 passing assets aren't at readiness 1.0: `topology.quad_ratio` is ~0.4 (voxel+decimate is mixed tris/quads, not clean quads), and LOD/collision validity + the Godot round-trip haven't been re-verified at the new budgets. Those are the next gate-level iterations.

## Honest status

The samurai — the original failure — is fixed and verified. 3/5 characters are game-ready at realistic budgets. But this is NOT "all 5 at AAA": one asset artifacts, one crashes, and the topology/LOD/Godot gates need more passes. This is a genuine multi-iteration effort; 3 iterations done, real ground gained, more remains.
