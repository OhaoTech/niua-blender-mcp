# Finding — multi-angle capture renders collapse (pre-existing)

**Date:** 2026-07-02 · **Status:** ROOT CAUSE FOUND + FIX VERIFIED LIVE.

## RESOLUTION

**Root cause:** setting `cam.location`/`cam.rotation_euler` does NOT synchronously update
`cam.matrix_world`; Blender defers the matrix recompute to a depsgraph pass that never lands
inside a single `system.execute_python` / bridge call. Every render path (`render.opengl`,
`render.render`, and GPUOffScreen when it reads `cam.matrix_world`) read the **stale** transform,
so all angles collapsed to one image. This is why the 5 attempted fixes failed — they all still
routed the render through the deferred transform.

**Verified fix (proven live on a cone — front renders a triangle, top a circle, 4/4 distinct):**
render via `gpu.types.GPUOffScreen.draw_view3d(scene, view_layer, space, region, view_matrix,
proj_matrix, do_color_management=False)` where **`view_matrix` is computed in PURE PYTHON from the
frame**: `(Matrix.Translation(loc) @ Euler(rot,'XYZ').to_matrix().to_4x4()).inverted()` — never
reading `cam.matrix_world`. Projection = `cam.calc_matrix_camera(depsgraph, x=res, y=res)` after
setting `cam.data.type`/`ortho_scale` (camera DATA updates immediately; only object TRANSFORMS are
deferred). Needs a live VIEW_3D area+region (GUI). Working prototype:
`scratchpad/gpu_offscreen_probe2.py`.

**Remaining for production:** disable viewport overlays (`space.overlay.show_overlays = False`) and
set `space.shading.type` per mode (SOLID for form/silhouette; MATERIAL for the topology/silhouette
emission fills) then RESTORE; read pixels bottom-up and flip; encode PNG; keep the graceful-degrade
contract (no VIEW_3D / no GL -> `available: False`).

---


## Symptom

The capture eyes (`feedback.capture`, `capture_views`, and therefore `feedback.topology`,
`feedback.silhouette`, and the altimeter's multi-angle judgment) frequently render **multiple
ortho angles identically** — front/right/top come back byte-identical while only `persp` differs.
On a cone (front=triangle, top=circle → must differ) all three orthos collapsed to one hash.

## Investigation (live, instrumented via system.execute_python)

- The camera object's `location`/`rotation_euler` ARE set correctly per view, and its
  `matrix_world` reflects distinct transforms per view.
- Yet the RENDER does not track the current camera: renders lag by one and/or collapse to a
  single ortho image. Behavior is **inconsistent across probes and objects** (a tall box once
  showed a distinct `top`; the cone never did).
- Tried and did NOT reliably fix: (1) `hide_viewport=False` on the capture cam; (2) assigning
  `cam.matrix_world` directly instead of loc+euler; (3) `evaluated_depsgraph_get().update()`;
  (4) `scene.frame_set(frame_current)`; (5) `bpy.ops.render.render()` (deterministic renderer)
  instead of `render.opengl(view_context=False)`. `render.render()` ALSO collapsed the orthos.

## Read

Since even the deterministic `render.render()` collapses the ortho views, the fault is in how the
camera transform is (not) evaluated for these programmatic per-view renders inside one bridge
call — a depsgraph/update-timing issue that black-box probing over the bridge isn't cracking
efficiently. This is an architecture question (Phase 4.5), likely wanting a different capture
path: **`gpu.types.GPUOffScreen` with an explicitly-supplied view+projection matrix** (fully
deterministic, viewport- and depsgraph-timing-independent) — which PLAN.md already flagged as a
deferred "GPUOffScreen non-intrusive" item.

## Impact (important — it's bounded)

- **Objective gates are UNAFFECTED.** `feedback.quality` (topology/uv/proportion/symmetry/…) is
  pure bmesh/vertex math, no rendering. The whole pipeline gate system stands.
- **`persp` renders correctly** and carried real per-object signal — the altimeter baseline
  (3.9/10, per-object scores tracked reality) is directionally valid, but its multi-angle
  strength was weaker than assumed; the ortho angles were largely redundant.
- The `feedback.silhouette` code (Phase 1 Wave 1) is itself correct; it inherits this capture
  limitation. Its flat-fill + proportion/symmetry numbers are still an improvement on `persp`.

## Options

1. Fix the capture engine first via a GPUOffScreen path (own focused wave, likely an
   interactive-Blender debugging session) — prerequisite for reliable multi-angle form perception.
2. Proceed with form perception on `persp`-only + `turntable` (which orbits and may not hit the
   same collapse) for now; revisit multi-angle later.
3. Pause and hand this specific render bug to a dedicated debugging session with deeper
   Blender-internal instrumentation.

---

## RESOLUTION 2 (the one that works) — 2026-07-02

GPUOffScreen `draw_view3d` proved unreliable (renders blank/inconsistent; no error logged).
**Verified-working approach instead: viewport-driven capture.** Drive the live 3D viewport to
each angle and capture what is actually drawn on screen:

```python
with bpy.context.temp_override(area=view3d_area, region=window_region):
    bpy.ops.view3d.view_axis(type="FRONT"|"RIGHT"|"TOP"|...)  # + view_orbit for 3/4 views
    bpy.ops.view3d.view_selected()                            # frame the (selected) subject
    scene.render.filepath = path
    bpy.ops.render.opengl(write_still=True, view_context=True)  # capture the VIEWPORT
```

Proven live on Suzanne: FRONT=face, RIGHT=profile, TOP=head — 3/3 distinct, correct, ~55KB each
(not blank). Prototype: `docs/reports/viewport_capture_verified_prototype.py`.

**Production requirements:** snapshot + restore the viewport view (`region_3d.view_matrix`/
`view_perspective`/`view_distance`) and the current selection/active object so the eye stays
non-intrusive; set `space.shading.type` (SOLID for form; MATERIAL for topology/silhouette emission
fills) + overlays off, then restore; degrade gracefully with no VIEW_3D/GL. This REPLACES the
GPUOffScreen `_render_offscreen` path added in P1.0.
