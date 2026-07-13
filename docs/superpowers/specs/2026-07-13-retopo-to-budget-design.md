# Retopo-to-Budget for bake_and_finish — Design

**Date:** 2026-07-13
**Status:** approved (brainstorm), pending spec review
**Branch:** new feature branch off main

## 1. The problem this closes

`bake_and_finish` (skill #2) takes 3/5 dense assets to the triangle budget at good surface fidelity,
but the 2 densest (`real_character` 77k organic, `real_prop`/samurai 978k hard-surface, likely
non-manifold) fail: the move **decimates** to budget, and a decimated 978k→5k mesh has junk topology
and garbage auto-UVs that the high→low bake cannot carry — surface_fidelity lands 0.28/0.34, below
the 0.60 floor, so the accept/revert loop honestly reverts them to high-poly (not game-ready).

The fix is a real **retopo** step (clean quads + clean UVs) before the bake, so the low-poly's
silhouette and UV layout can hold the baked detail. The `surface_fidelity` ruler already grades
whether retopo+bake beats decimate+bake — no new metric.

## 2. The retopo pipeline (decided): voxel-remesh → quadriflow-to-budget

Blender ships both ops in the committed manifest (reachable today via `capabilities.invoke`); no
curated retopo tool exists.

- **Voxel remesh first** (`object.voxel_remesh`): robust on garbage — rebuilds any non-manifold /
  self-intersecting generator mesh into a clean, watertight, manifold surface, and drastically cuts
  the poly count. This is what makes the 978k non-manifold samurai survivable (quadriflow alone
  often fails or hangs on such input) AND makes the whole thing faster (quadriflow then runs on the
  reduced voxel mesh, not 978k tris).
- **Quadriflow to budget** (`object.quadriflow_remesh`, mode=FACES, target_faces): clean, adaptive
  all-quad topology at the triangle budget.

The voxel pass slightly softens the sharpest hard edges; the bake then restores that as normal-map
detail — which is the point. Rejected alternatives: quadriflow-only (fragile on the exact failing
non-manifold assets), voxel-only (uniform density wastes budget on flat panels — weaker for
hard-surface).

## 3. Components

### 3.1 `object.retopo` — a curated interface tool (both sides + SDK)
A focused primitive: voxel→quadriflow, **topology only** (UV + bake stay in the skill, matching how
`_bake_transfer` composes primitives today). Curated — not raw `capabilities.invoke` — so it is
typed, validated, undo-safe, and appears in the SDK as `session.object.retopo(...)`, consistent with
every other finishing primitive.
- Params: `object: Str(required)`; `target_faces: Int` (the budget, in faces); `voxel_size: Float`
  (default 0) where 0 = auto-derive from the object's bbox (a fraction of the longest bbox axis so
  the voxel mesh is clean but not astronomically dense); `adaptivity: Float` (quadriflow/voxel
  adaptivity, default 0). `mutates=True`, `timeout_tier="heavy"` (quadriflow is slow).
- Behavior: run `object.voxel_remesh` (auto voxel_size when 0), then `object.quadriflow_remesh` with
  `mode="FACES"`, `mesh_area=-1`, `target_faces=target_faces`, `use_preserve_sharp`/`use_preserve_boundary`
  as sensible defaults. Returns `{object, faces, tris}` after retopo.
- **Fail cleanly (no silent fallback):** if either remesh op fails/raises, the tool raises a
  structured error (PRECONDITION/INTERNAL). It never falls back to a low-quality decimate — a failed
  retopo surfaces honestly rather than shipping garbage.

### 3.2 `bake_and_finish` move amendment (policy)
`_bake_transfer` swaps its decimate step for `object.retopo`:
duplicate high-poly → **`session.object.retopo(object=subject, target_faces=budget//2)`** (quads;
budget is in *triangles*, quadriflow targets *faces*, so ≈ budget/2 quad faces) → `mesh.select_all`
→ `uv.smart_unwrap` → `uv.pack_islands` → `object.bake_transfer(source=high, target=subject)` →
delete high source. Everything else in the skill (the harm gate on silhouette AND surface_fidelity,
the accept/revert loop, stray cleanup) is unchanged. `TOOLS_USED` gains `object.retopo`.

`make_game_ready` (skill #1, decimate-based) is UNTOUCHED, so its byte-identical benchmark reading
does not move.

### 3.3 No new metric
`surface_fidelity` grades this directly. Success = retopo+bake scores materially higher than the
recorded decimate+bake (0.28/0.34), ideally ≥ 0.60 (KEPT to budget).

## 4. Robustness stance (the one design call to confirm)

**No decimate fallback inside the move.** If retopo fails, the move reverts and the asset stays
high-poly (honest decline) — never a silent fall back to the garbage-producing decimate. Worst case
is therefore *no regression* vs today's behavior (the 2 assets already revert to high-poly); expected
case is they now cross the floor. A bad retopo produces low fidelity and reverts, exactly like a bad
decimate does now — no new failure mode.

## 5. Layer / architecture
`object.retopo` is interface (generic Blender op); the skill amendment is policy. Parity (both
sides), layer boundary, and the SDK drift test all apply. The SDK is regenerated so
`session.object.retopo` exists.

## 6. Testing
- Offline: `object.retopo` registered both sides with parity (mutates=True, timeout_tier="heavy",
  params); the SDK exposes `session.object.retopo`; param validation (target_faces > 0). The remesh
  itself is live-validated (GL/remesh ops).
- `bake_and_finish` skill test: `_bake_transfer` now calls `object.retopo` (not decimate) — a
  FakeSession test asserting the retopo call is issued with the budget-derived target.
- LIVE acceptance: run `bake_and_finish` on the 5 assets; the 2 previously-failing dense assets score
  materially higher surface_fidelity than decimate (0.28/0.34) and, ideally, cross the 0.60 floor to
  be KEPT at budget. The 3 previously-passing assets stay passing (no regression). Before/after
  captures of the samurai/character. Honest report: if the samurai still can't cross the floor at its
  tight budget, that's a real finding (budget vs silhouette), not a failure — the number tells us.

## 7. Constraints carried forward
ZERO niua knowledge; parity + boundary + SDK-drift green; `make_game_ready` + its benchmark reading
unchanged; full offline suite green; the remesh is deterministic enough for the ruler (quadriflow is
deterministic for a fixed target; voxel is deterministic for a fixed size).

## 8. Success criteria
1. `object.retopo` (voxel→quadriflow) exists, both sides + SDK, fails cleanly.
2. `bake_and_finish` uses it instead of decimate; skill #1 untouched.
3. LIVE: the 2 densest assets score materially higher fidelity than decimate; the goal is 5/5 KEPT
   to budget, with any residual shortfall reported honestly with the number.
4. Everything green: offline suite, parity, boundary, SDK drift; the 3 already-good assets don't
   regress.
