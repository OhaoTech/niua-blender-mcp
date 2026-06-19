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

## Phase 2 — UV, shading, modifiers, animation, rigging

- [ ] `uv` (unwrap methods, pack), `shading` (material + node trees), `modifiers`,
      `anim` (keyframes/actions), `rig` (armature/weights). One pack at a time.

## Phase 3 — RNA generation + context hardening

- [ ] Generation pass over allowlisted operator categories → curated-quality ToolSpecs.
- [ ] `rna.call_operator` / `rna.set_property` generic execution.

## Phase 4 — Feedback depth + io + headless workers

- [ ] Multi-angle/turntable, UV/topology/diagnostic captures; `GPUOffScreen` non-intrusive.
- [ ] `io` import/export (the niua asset seam; Godot-ready glTF).
- [ ] Async heavy ops (modal operators), headless worker pool, the critique loop.
