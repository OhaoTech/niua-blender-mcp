# Build Plan

Architecture: [`DESIGN.md`](DESIGN.md). Each phase keeps the kernel untouched and adds
domain packs. TDD with fake-bpy unit tests + the real-Blender smoke test.

## Phase 0 — Kernel + proof  ✅ DONE

The hard part, built once and verified end to end against real Blender (39 tests green).

- [x] Kernel: `ToolSpec` contract + validation/coercion (`Vec3` included), structured
      error model, router with curated-over-rna precedence and lazy categories.
- [x] Add-on dispatch core: `Command`/`Registry`, `dispatch_on_main` with one undo step
      per mutation and rollback-on-failure, execution `Context`.
- [x] `scene` domain: `info`, `create_object`, `set_transform`.
- [x] `rna.describe` introspection primitive (operators + types from live RNA).
- [x] `feedback.capture` (viewport PNG → MCP image; degrades gracefully headless).
- [x] Gated `system.execute_python` escape hatch.
- [x] TCP bridge client; hand-rolled zero-dep MCP stdio server; `__main__` entry.
- [x] Add-on runtime: socket server + main-thread drain (GUI timer + headless loop),
      N-panel Start/Stop, register/unregister.
- [x] Headless launcher + smoke test: create → move → read, RNA describe, clean error
      without crashing Blender, feedback verdict.
- [x] Server↔add-on command parity test.

**Demonstrated:** in headless Blender the agent reads the scene, creates and moves an
object, introspects the live API, and a bad call returns a structured `not_found`
without crashing. In a GUI session the same runs with a visible window and per-action
Ctrl+Z. The spine holds; everything below is "add a domain pack."

## Phase 1 — Mesh editing  ✅ DONE

Verified end to end against real Blender 5.1 headless (73 tests green, incl. a mesh
edit smoke: cube → `mesh.subdivide` cuts=2 → `mesh.report` confirms 8/12/6 → 56/108/54).

- [x] Edit-mode context manager in the kernel (`ctx.ensure(mode='EDIT', ...)`) + `poll()`
      precondition checks (the context resolver from DESIGN §7.5). Headless-safe: skips
      the `temp_override` when no VIEW_3D area exists; one undo step pushed only after a
      successful mutation, never on a precondition failure.
- [x] `mesh` domain: extrude, bevel, inset, subdivide, recalc_normals, shade_smooth
      (select/loop-cut/merge deferred to Phase 2 alongside the wider edit toolkit).
- [x] Analytic feedback: `mesh.report` (tris, n-gons, non-manifold edges via bmesh, bbox
      dimensions, UV/material counts, transform-applied check).

## Phase 2 — UV, shading, modifiers, animation, rigging  ✅ DONE

Five domain packs built concurrently, integrated, and verified end to end against real
Blender 5.1.1 headless (161 tests green, incl. one safe smoke op per pack). Parity holds
across all server SPECS ↔ add-on COMMANDS.

- [x] `uv` — smart_unwrap, unwrap (ANGLE_BASED/CONFORMAL), cube/sphere project,
      pack_islands, average_islands_scale, report (has_uvs, layers, island_count via bmesh).
- [x] `shading` — create_material, set_principled (Base Color/Metallic/Roughness/Alpha/
      Emission Strength sockets verified in 5.x), assign_material, add_image_texture,
      list_materials.
- [x] `modifiers` — add (SUBSURF/BEVEL/SOLIDIFY/MIRROR/ARRAY/BOOLEAN/DECIMATE/WIREFRAME),
      set (typed coercion), apply, remove, list.
- [x] `anim` — set_frame, insert/delete keyframe, set_interpolation, list_actions, report.
      Slotted-action aware: f-curves read from `action.layers[].strips[].channelbag(slot)`
      on Blender 4.4+ (legacy `action.fcurves` removed in 5.x) with a flat-list fallback.
- [x] `rig` — add_armature, add_bone, set_bone_transform (edit-bone authoring survives the
      EDIT→OBJECT round-trip), parent_with_auto_weights (heat skinning works headless),
      list_bones.

## Phase 3 — Live RNA discovery + generic execution  ✅ DONE

Uncapped coverage without flooding `tools/list`: instead of mass-generating hundreds of
static ToolSpecs (which rot on every Blender version bump), the agent *discovers* the
live API and *executes* anything it finds through the existing validate → `ctx.ensure`
→ undo pipeline. Verified end to end against real Blender 5.1.1 headless (193 tests green,
incl. Phase-3 smoke for search, generic create, generic EDIT-mode mesh edit, generic
OBJECT-mode resize, and a set/get property round-trip drift guard). Parity holds; no
kernel-contract change.

- [x] `rna.search` — mines live `bpy.ops` + `bpy.types` for operators/types matching a
      query, relevance-ranked (idname > label > description; exact > prefix > substring),
      filtered by `category`/`kind`, skips UI/system categories, requires real help text.
- [x] `rna.call_operator` — runs any `bpy.ops.<cat>.<name>`; args validated/coerced against
      the operator's own RNA (unknown keys dropped, numbers/enums coerced, POINTER/
      COLLECTION ignored with a note); eager `get_rna_type()` probe → clean `not_found`
      for bogus ids; `ctx.ensure(active/mode/select)` + `ctx.check_poll` for context.
- [x] `rna.set_property` / `rna.get_property` — read/write any dotted path under `bpy.data`
      (attribute access + collection-by-name fallback), value coerced toward the live type.
- [x] Args/value/select cross the bridge as JSON-encoded strings (no new param kind, no
      kernel-contract change — all contract/parity tests stay green).

**Context hardening (honest about headless vs GUI):** generic EDIT-mode operators work
headless — `rna.call_operator('mesh.subdivide', mode='EDIT', ...)` takes a factory cube
8v/6f → 26v/24f with no VIEW_3D area (the resolver skips `temp_override` and `mode_set`
drives the switch). OBJECT-mode ops (`transform.resize`) mutate as expected. Callers must
pass `mode` for edit-mode operators (not inferred); documented in the ToolSpec summaries.
Operators that *require* a real VIEW_3D area/region (e.g. view-dependent selection, some
gizmo/UI-driven ops) cannot be poll-verified headless and need a later GUI pass.

## Phase 4 — Feedback depth + io + headless workers

- [x] Multi-angle/turntable captures (the anti-blob): `feedback.capture` (one named view
      or the live scene camera), `feedback.capture_views` (presets ortho4/ortho6/orbit4),
      `feedback.turntable` (orbit). A dedicated hidden capture camera (`__niua_capture_cam`)
      is created once and reused; the user's viewport camera/view is never touched, and every
      per-render scene mutation (camera/engine/resolution/filepath/format) is snapshotted and
      restored. Framing math (bbox → view/orbit camera placement, ortho-scale) is pure-Python
      and unit-tested under fake-bpy; the server emits one MCP image content per available
      image. All read-only (`mutates=False`), parity holds. Degrades to `available:false`
      headless (no GPU) — the envelope/contract is asserted in headless smoke
      (`test_feedback_capture_views_returns_envelope`, `test_feedback_turntable_returns_envelope`).
      **The actual rendered multi-angle/turntable PNGs are verified in a GUI session, not
      headless** (pure `--background` with no GL context returns the graceful degrade).
- [ ] UV/topology/diagnostic captures; `GPUOffScreen` non-intrusive.
- [ ] `io` import/export (the niua asset seam; Godot-ready glTF).
- [ ] Async heavy ops (modal operators), headless worker pool, the critique loop.
