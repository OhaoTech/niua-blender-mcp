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

## Phase 4 — Feedback depth + io + headless workers  ✅ DONE (depth carried into Phase 6)

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
- [x] `io` import/export (the niua asset seam; Godot-ready glTF). Four tools, all
      auto-discovered, parity holds, verified end to end against real Blender 5.1.1
      headless (243 tests green): `io.import` (AUTO format inference by extension; new
      objects via scene before/after diff), `io.export_gltf` (GLB/separate, selection,
      apply-modifiers, +Y up), `io.export` (generic GLB/FBX/OBJ router), `io.prepare_godot`
      (apply transforms then export one object to Godot-ready GLB). Headless smoke proves
      the full seam: export writes a non-empty GLB (verified `glTF` magic), a round-trip
      re-imports at least one mesh object, and prepare_godot applies transforms
      (location→0, scale→1) before exporting. Exports stay `mutates=False` (selection set
      only for the call, restored on exit). Operator ids confirmed on 5.1.1 below.
      **Decoupling held:** the domain only moves files; it knows nothing about niua or Godot.
- [ ] Async heavy ops (modal operators), the critique loop (Phase 6).

**Headless worker mode vs worker pool.** A single headless worker
(`serve_blocking` / the `scripts/blender_serve.py` launcher driving the socket bridge on
the headless main-thread loop) already exists from Phase 0 and is what every real-Blender
smoke test runs against — `blender --background` serving the bridge over TCP. A worker
**pool** (multiple concurrent headless Blender instances behind one MCP server for
parallel/async heavy ops) is **deferred to a later pass** alongside modal operators in
Phase 6; it is not required for the io seam, which is synchronous file in/out.

**Operator ids verified on Blender 5.1.1 (this build).**
- Import: `import_scene.gltf` (GLTF+GLB share one importer), `wm.obj_import`,
  `import_scene.fbx`, `wm.stl_import`, `wm.usd_import`, `wm.ply_import`, `wm.alembic_import`.
- Export: `export_scene.gltf` (kwargs `filepath`, `export_format`, `use_selection`,
  `export_apply`, `export_yup` all present), `export_scene.fbx` (`filepath`,
  `use_selection`), `wm.obj_export` (`filepath`, `export_selected_objects`).
- `object.transform_apply(location=, rotation=, scale=)` for `io.prepare_godot`.
- **Collada (DAE) is NOT available in this build:** `bpy.app.build_options` has no
  `collada` flag (OpenCollada was dropped), so `wm.collada_import`/`wm.collada_export`
  do not resolve. The `getattr` on `bpy.ops` returns a lazy callable (does not raise), so
  a DAE import reaches the operator call and raises `AttributeError("...could not be
  found")`, which the add-on dispatch normalizes to a clean structured `handler_error`
  (Blender does not crash). DAE remains advertised in `IMPORT_FORMATS`; on a Collada-less
  build it degrades to that structured error rather than a precondition. Harden later if
  DAE matters (probe `build_options.collada` and raise `precondition_failed` up front).

## Phase 6 — the critique loop  ✅ DONE

The project's ORIGIN problem: blind one-shot text→model produces blobs because a single
generation step has no perceptual feedback. The answer (DESIGN §10, §12, §"Phase 6") is
deliberate ops + faithful multi-angle eyes + an **iterating multimodal agent**. The critic
is the agent itself; the MCP ships the two *primitives* that make the loop tight, never an
autonomous Python loop. Verified end to end against real Blender 5.1.1 headless (262 tests
green, incl. the server↔addon parity test).

- [x] `session` domain (SAFE-ITERATE beyond Blender's single-op undo) —
      `session.checkpoint` (snapshots `obj.data.copy()` + transform into a dedicated store;
      non-destructive, so `mutates=False`), `session.revert` (swaps a *fresh* copy of the
      snapshot back + restores transform; one undo step, `mutates=True`; clean `not_found`
      when no such checkpoint), `session.list_checkpoints` (read-only, oldest-first). The
      store (`core/session.py`) is independent of Blender's fragile, human-shared undo
      stack, so a multi-step edit gone worse rolls back cleanly. No `getattr`-on-`bpy.ops`
      probing introduced (prior-phase lesson). **Headless-proven backbone:** cube →
      `session.checkpoint` → `mesh.subdivide` cuts=2 (8/12/6 → 56/108/54) → `session.revert`
      → `mesh.report` back to 8/12/6 (`test_session_checkpoint_revert_round_trip`).
- [x] `feedback.critique` (the one OBSERVE call) — bundles `feedback.capture_views`
      (multi-angle taste signal, the anti-blob) with `mesh.report` (checkable facts) and,
      for a mesh, `uv.report`, in one round-trip:
      `{ available, images:[…multi-angle…], report:{…mesh.report…}, uv:{…uv.report|null} }`.
      Reuses the existing handlers (imported, not duplicated — both still work standalone),
      `mutates=False`. The analytic half returns real geometry headless; the rendered-pixel
      half degrades to `available:false` with no GL context. **Headless-proven envelope:**
      `feedback.critique` on a cube returns the bundle shape with a `report` of 8v/12e/6f
      (`test_feedback_critique_returns_bundle_envelope`).

### Critique loop — objective metrics  ✅ DONE

The images give the (multimodal) agent *taste signal*; on their own the loop still converges
on vibes. `feedback.quality` adds the **objective judgment channel** — pure-geometry numbers
(bmesh + vertex coords, no GPU) that the agent checks alongside the rendered angles, so
do→observe→judge→revert converges on facts. `mutates=False`; param `object` optional → active
mesh; non-mesh → clean precondition error.

- [x] `feedback.quality` returns four blocks:
      **topology** (`faces`, `tris`, `quads`, `ngons`, `quad_ratio`, `ngon_ratio`,
      `pole_count` = interior verts with edge-valence ≠ 4, boundary/non-manifold verts
      excluded; `non_manifold_edges`; `loose_verts`) — the three bmesh fields degrade to
      `null` when bmesh is unavailable, the face counts always compute;
      **symmetry** (`symmetry_x/y/z` = fraction of verts with a mirror partner across the
      local plane normal to each axis, ε=1e-4, grid-bucketed ≈linear, pure geometry);
      **proportion** (`bbox_dimensions`, `aspect_ratio`, `boxiness`);
      **scale** (`bbox_dimensions`, `transform_applied`).
- [x] Shared-helper refactor: `topology_counts`, `bbox_dimensions`, `transform_applied`,
      `_bmesh_for` factored out of addon `mesh.py`; `mesh.report` consumes `topology_counts`
      with its original fields unchanged. LESSON kept: metrics come from bmesh/mesh data,
      never from `getattr` on lazy `bpy.ops` stubs.
- [x] Folded into `feedback.critique`: the bundle's `report` carries a compact `quality`
      sub-dict (`quad_ratio`, `ngon_ratio`, `pole_count`, `non_manifold_edges`, `loose_verts`,
      `symmetry`, `aspect_ratio`, `transform_applied`) for a mesh, best-effort (never breaks
      the bundle). One OBSERVE call → images + counts + quality.
- [x] **MCP prompts** (`prompts.py`): `refine_mesh` scaffolds the loop
      (`session.checkpoint` → one edit → `feedback.critique` → judge silhouette/symmetry/
      topology against concrete targets → keep+re-checkpoint or `session.revert` → repeat) and
      `inspect` scaffolds a read-only assessment (`scene.info` → `feedback.critique` →
      `feedback.quality`). Both take an optional `object` arg. Server wired: `prompts/list`
      returns real metadata, `prompts/get` renders messages (unknown/missing → INVALID_PARAMS),
      `initialize` announces the `prompts` capability. Generic Blender workflows — no
      pipeline-specific references.
- [x] **Headless-proven on real Blender 5.1.1** (pure geometry, no GPU):
      a default cube → `quad_ratio == 1.0`, `ngons == 0`, `non_manifold_edges == 0`,
      `loose_verts == 0`, `symmetry_x/y/z == 1.0`, and **`pole_count == 8`** — note this is the
      geometrically correct value, not 0: a cube's 8 corners are all valence-3 with manifold
      edges, so none are excluded as boundary and every corner counts as a pole; the cube has
      no valence-4 interior verts at all. Suzanne (`mesh.primitive_monkey_add`) → `faces > 400`,
      `symmetry_x > 0.9` (left-right symmetric) with `symmetry_x` dominating `symmetry_y`, and
      real poles/non-manifold edges populated. The `critique` bundle's folded `quality`
      sub-dict carries the cube's real numbers headless. Prompts: `prompts/list` non-empty and
      `prompts/get refine_mesh` mentions checkpoint/critique/revert. (`test_smoke_headless.py`:
      `test_feedback_quality_on_default_cube`, `test_feedback_quality_on_suzanne`,
      `test_feedback_critique_bundle_includes_quality_subdict`, `test_prompts_list_is_non_empty`,
      `test_prompts_get_refine_mesh_scaffolds_the_loop`.)

## Layer 1 capability surface  ✅ DONE

The complete discoverability foundation is now in place: a committed Blender 5.1
manifest, the `capabilities` front door, generated tier-2 typed catalogs, and
live drift checks. This makes every reachable Blender operator findable and
invokable through a small default tool surface, while keeping curated tools first.

- [x] **Manifest.** `scripts/gen_manifest.py` runs inside Blender and writes
      `src/niua_blender_mcp/manifest/blender_5_1.json`; the offline loader supports
      search/describe and ships the JSON as package data.
- [x] **Tiered router.** `ToolSpec.tier` distinguishes curated/generated/reflection;
      router precedence keeps curated specs ahead of generated/reflection entries and
      exposes a lightweight index.
- [x] **Capabilities front door.** `capabilities.domains/search/describe/invoke`
      is registered on both server and add-on sides. Runtime search/describe uses
      live RNA; invoke delegates through the same undo-safe `rna.call_operator` path.
- [x] **Tier-2 generator.** Manifest allowlists emit generated typed specs such as
      `modeling.subdivide`, hidden from `tools/list` by default but callable by name
      and routed through `capabilities.invoke`.
- [x] **Coverage/drift smoke.** The real-Blender smoke test verifies
      `capabilities.search` finds `mesh.bevel` and sampled manifest operators still
      describe through live RNA.

Remaining layer-1 fill is additive: expand the manifest domain allowlists over time.
Layer 2 remains a separate spec: senior craft verbs, judgment playbooks, deeper
eyes, and game-pipeline conventions.

## Layer 2 Phase A vertical slice  ✅ DONE

The senior-artist scaffold now has a proven modeling/topology vertical slice:
topology eye, deterministic gate checker, modeling battery plus harness and judge
stub, playbook store, retopo seed recipe, and `model.retopo_quads`. Wave 2
(UV/bake/materials) and the Phase B convergence loop are next.

## Project status — 7-phase plan COMPLETE  ✅

All seven phases (0–6) are shipped and verified end to end against **real Blender 5.1.1
headless**, not just fake-bpy: 262 tests green including the server↔add-on command-parity
test, with **55 curated tools across 13 domains** (scene, mesh, uv, shading, modifiers,
anim, rig, io, feedback, session, plus the `rna` discovery/exec, introspection, and gated
`system` escape hatches). Every phase added a domain pack without touching the kernel
contract, kept handlers tiny, pushed exactly one undo step per successful mutation, and
held parity. The full agentic spine is exercised headlessly: read → create/move →
introspect live RNA → edit mesh/uv/shading/modifiers/anim/rig → export Godot-ready glTF →
checkpoint/edit/revert (safe iterate) → critique bundle (analytic facts). The **only** part
that remains a GUI/GPU demonstration is the *rendered pixels* of the eyes — the actual
multi-angle/turntable/critique PNGs — which require a live GL context and so come back
`available:false` in pure `--background`; their final visual proof is a GUI session, by
design. The critique *loop* is agent behavior driving these primitives, not a Python loop.
