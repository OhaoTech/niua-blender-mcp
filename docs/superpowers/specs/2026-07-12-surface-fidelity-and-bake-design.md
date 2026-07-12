# Surface Fidelity + Bake-Transfer — Design (skill #2, ruler-first)

**Date:** 2026-07-12
**Status:** approved (brainstorm), pending spec review
**Branch:** lean-rebuild

## 1. The problem this fixes

The finisher's do-no-harm metric is **silhouette IoU only** — it measures the outline, not the
surface. So a decimation that crushes surface detail into facets *passes* preservation
(the troll/samurai scored silhouette 0.87–0.97 while looking like garbage) and the accept/revert
loop keeps it. The finisher also has **no real bake**: `shading.prepare_pbr_maps` creates empty
image slots, and `_decimate_to_budget` throws the high-poly detail away instead of transferring it.
The result violates the founder's quality bar ("the finished asset must look almost identical to the
input; game-ready is what changes underneath").

Two things are needed, in ruler-first order: **(A)** a surface-fidelity metric that catches the
detail loss the silhouette misses, then **(B)** a bake-transfer move that decimates to a low-poly and
bakes high→low detail so the surface *is* preserved — delivered as a graded skill, and gated by the
metric so a detail-destroying step reverts automatically.

## 2. Ruler-first sequencing (binding)

- **Phase A builds the metric and PROVES it before any bake code exists.** Validation gate:
  self-fidelity of an unchanged mesh ≈ 1.0 (deterministic), AND the metric must **flag the known-bad
  case** — re-running the current `make_game_ready` decimate on the dense assets must drop
  `surface_fidelity` well below the floor on exactly the assets where silhouette IoU wrongly passed.
  A metric that cannot catch the troll does not earn the right to grade the bake; if the gate fails,
  fix the metric, do not proceed to Phase B.
- **Phase B builds the bake move + skill #2, graded by the now-trusted metric.**

## 3. The fidelity signal (decided)

- **Shaded, normal-map-applied render** (not a flat silhouette, not a pure-geometry matcap): the
  metric renders the object as it would look in-engine, so a baked normal map affects the shading.
  This grades the *whole* bake workflow — a raw decimate shades blocky (low fidelity → reverted); a
  good bake (low-poly + baked normal) shades like the high-poly (high fidelity → kept).
- **Neutral clay material + one fixed sun, shade-smooth, fixed ortho frames.** The render uses a
  neutral base color and the object's normal map (when present) — NOT the asset's albedo textures —
  so the metric isolates *surface shape*, the thing the bake preserves/destroys. Colour/albedo
  fidelity is a separate concern (generator textures usually survive) and out of scope here.
- **SSIM scoring**, single-channel luminance, over the separable masked region, **mean across views,
  min-view reported, fail-closed** — same discipline as the silhouette min-view. SSIM (structural,
  windowed) is chosen over mean-abs/gradient because it tracks "looks the same to a human": a global
  brightness shift barely moves it, but lost surface structure (facets, smeared detail) tanks it —
  exactly the troll failure. Deterministic at the small (256²) render size.

## 4. Architecture & layer placement

```
INTERFACE (generic measurement)
  core/fidelity_metrics.py        [NEW] pure stdlib: PNG->luma, windowed SSIM, mean_fidelity(min/fail-closed)
  core/silhouette.py              [EXTEND] a shaded fixed-frame pass (neutral clay + fixed sun) beside the alpha pass
  core/preservation_ledger.py     [EXTEND] store the shaded intake baseline beside the intake masks
  domains/finishing_feedback.py   [EXTEND] capture_intake stores shaded baseline; preservation returns surface_fidelity
  domains/<bake>.py               [NEW] the real high->low bake tool (mutates)  -- interface: a generic Blender op

FINISHING / POLICY
  finishing/<fidelity floor>      [NEW] SURFACE_FIDELITY_FLOOR constant (the policy threshold)
  finishing/skills/bake_and_finish.py  [NEW] skill #2: bake-aware finishing, gated on silhouette AND fidelity
  evals/objective_bench + scorecard    [EXTEND] surface_fidelity axis + harm considers both preservation axes
```

**Boundary:** the SSIM core, the shaded render, and the bake operator are generic measurement/action
→ interface. The fidelity *floor* and the *skill* are opinionated → policy. `test_layer_boundary.py`
stays green.

## 5. Components

### 5.1 `core/fidelity_metrics.py` (Phase A, pure stdlib)
Mirrors `silhouette_metrics.py`. Functions:
- `png_b64_to_luma(data_b64) -> (w, h, luma_bytes)` — decode 8-bit PNG to single-channel luminance
  (reuse the existing PNG decoder path; luminance = 0.299R+0.587G+0.114B, or the existing luma path).
- `ssim(a_luma, b_luma, w, h, mask, window=8) -> float | None` — windowed SSIM over masked pixels;
  `None` if the masked region is too small to be separable (fail-closed).
- `mean_fidelity(intake: dict[view,(luma,mask)], current: dict[view,(luma,mask)]) -> dict` — per-view
  SSIM over the common separable views, returns `{available, fidelity(mean), per_view, min_view}`.
  Unmeasurable (no common separable view) → `available:false`.

### 5.2 Shaded render pass (Phase A, extend `core/silhouette.py`)
A `render_fidelity_views(bpy, obj_name, *, frame, views, res)` beside `render_preservation_views`:
same fixed ortho camera + frame + subject isolation, but shading = **EEVEE material render with a
neutral clay Principled material, one fixed sun lamp, shade-smooth, `film_transparent=True`** (RGBA,
so the alpha gives the mask for the SSIM region and the RGB gives the shaded luminance). EEVEE
specifically — Workbench shades by geometry normals and ignores material normal maps, which would
silently reduce this to the rejected pure-geometry signal; EEVEE applies the baked normal map so the
metric grades the actual finished look. Deterministic (fixed light, no denoise/AA dither/temporal
sampling). Fully restores all render state (same snapshot/restore pattern as the existing pass).
Degrades to `{available:false}` headless.

### 5.3 Ledger + feedback extensions (Phase A)
- `preservation_ledger`: `set_intake` also stores the shaded baseline (compact-encoded luma + mask +
  frame), beside the existing masks. Backward compatible (old records lack it → fidelity unmeasured).
- `feedback.capture_intake`: renders + stores the shaded baseline in the same call (fail-closed: if
  the shaded pass is unavailable, silhouette baseline still stored; fidelity simply unmeasured later).
- `feedback.preservation`: returns
  `{available, preservation(silhouette IoU), surface_fidelity: {available, fidelity, per_view,
  min_view}, ...}`. The silhouette field is unchanged (existing consumers unaffected); fidelity is
  additive.

### 5.4 The bake tool (Phase B, new interface op, `mutates=True`)
A generic high→low bake, `object.bake_transfer` with params
(source high-poly, target low-poly, maps = normal[+AO], ray distance/cage, image size). It runs
`bpy.ops.object.bake` (EEVEE/Cycles bake) selected-to-active high→low into the low-poly's UV'd image
maps, and plugs the normal map into the low-poly's Principled BSDF normal input so it shades with the
baked detail. Undo-safe, main-thread, validated params — same contract as every tool.

### 5.5 `bake_and_finish` skill (Phase B, skill #2 in the code-mode substrate)
The bake-aware finishing pass over the SDK: repair → **bake-transfer to budget** (duplicate the
intake high-poly as source, decimate/retopo a low-poly to the triangle budget, UV-unwrap it, bake
normal+AO high→low, wire the normal map) → UV pack → materials → LOD → collision → apply-transform.
Every step runs the accept/revert loop, now gated on **readiness held AND silhouette ≥ floor AND
surface_fidelity ≥ SURFACE_FIDELITY_FLOOR**. A decimate/step that destroys surface detail without
baking now fails the fidelity gate and reverts automatically. `make_game_ready` (skill #1) is left
untouched, so the byte-identical benchmark gate for the existing path still holds.

### 5.6 Scoring integration (Phase B)
`evals/objective_bench` + `scorecard`: add a `surface_fidelity` axis alongside readiness/preservation
(reported, unmeasured-≠-failed); `harm_flagged` fires when *either* silhouette *or* fidelity is
measured-and-below-floor. The benchmark grades `bake_and_finish` on all axes.

## 6. Testing

- `tests/core/test_fidelity_metrics.py` (offline, pure): SSIM of identical images = 1.0; SSIM of an
  image vs a blurred/faceted version drops materially; masked region excludes background; too-small
  region → None (fail-closed); mean/min/per-view aggregation correct.
- Ledger + feedback unit tests: capture_intake stores the shaded baseline; preservation returns the
  additive `surface_fidelity` field; unmeasured shaded pass → fidelity `available:false`, never a fake
  score; existing silhouette field unchanged.
- Bake tool unit tests (fake-bpy where possible; live-only parts noted): param validation, plugs the
  normal map, degrades cleanly when bake unavailable.
- `bake_and_finish` skill test (FakeSession, behavior-driven like the finisher tests): a step that
  drops fidelity below floor is reverted; a step that holds both axes is kept.
- **LIVE validation gate (Phase A, before Phase B):** self-fidelity ≈ 1.0 on an unchanged mesh; the
  raw `make_game_ready` decimate on the dense assets drops `surface_fidelity` below floor where
  silhouette passed — the metric provably catches the troll.
- **LIVE acceptance (Phase B):** `bake_and_finish` on the 5 assets — the finished low-poly's
  `surface_fidelity` is high (near the high-poly), readiness climbs, and the before/after captures
  show a result that looks almost identical to the input (the troll no longer garbage).

## 7. Constraints carried forward

- ZERO niua knowledge; parity green; interface/finishing boundary green; `make_game_ready` +
  its benchmark reading unchanged (new skill, additive metric field); full offline suite green;
  determinism (fixed light/frame, no denoise) so the metric is stable and judge-free.

## 8. Success criteria

1. `surface_fidelity` metric exists, is pure/deterministic, self-fidelity ≈ 1.0, and **flags the
   known-bad decimate** (validation gate passed) before any bake code.
2. A real high→low bake tool exists and shades the low-poly with the baked normal.
3. `bake_and_finish` skill produces a finished asset whose `surface_fidelity` is high and whose
   before/after captures look almost identical — the founder quality bar met on the dense assets.
4. The fidelity axis is in the scorecard; `harm_flagged` honors both preservation axes.
5. Everything green: offline suite, parity, boundary, and the existing `make_game_ready` benchmark
   reading byte-identical.
