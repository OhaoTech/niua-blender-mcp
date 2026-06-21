# Design — Complete Capability Surface (Layer 1)

**Date:** 2026-06-20
**Status:** Approved (design); implementation plan to follow
**Scope:** Layer 1 of the niua Blender MCP — the complete, discoverable, validated capability surface. The senior-artist intelligence layer (layer 2) is named here but specified separately.

---

## 1. Context

The repo already has a working spine (built across 7 earlier phases): a kernel
(`ToolSpec` contract + `Router`), 13 self-registering domains, ~55 curated tools,
two escape hatches (`rna.search`/`rna.describe` live introspection;
`rna.call_operator`/`set_property`/`get_property` generic execution), an
observe→checkpoint→iterate loop, and "eyes" (multi-angle capture + analytic
metrics). It runs against real Blender 5.1.x with ~281 tests. The agent-driven
critique loop demonstrably converges.

**The gap.** `execute_python` (and the `rna.*` escape hatches) already make 100%
of Blender *reachable*. So the missing thing is not raw access — it is that the
full surface is not exposed as **discoverable, validated, undo-safe, addressable
capability**. The agent cannot reliably *find* the right operation among
thousands, cannot get a *typed schema* for an arbitrary operator before calling
it, and the escape hatches validate only against *live* RNA at call time (no
committed, browsable catalog).

**The bar (north star).** Output that competes with 30 years of senior
technical-artist expertise. Layer 1 does not reach that bar by itself; it is the
foundation that makes the senior-artist layer (layer 2) possible. Layer 1 is
"done" when the agent can *reach and correctly invoke* every capability a senior
would; layer 2 is "done" when its *output* passes a senior task battery.

## 2. Product definition

**niua Blender MCP** — a standalone MCP that exposes the entire **3D-craft**
surface of Blender to an AI agent as discoverable, validated, undo-safe
capability, then layers senior technical-artist judgment on top.

- **Standalone / decoupled.** Zero knowledge of niua. Blender files are generic
  inputs via the existing `io` domain. Any orchestrator wiring lives one level up
  in niua's own repo, never here.
- **Visible-first.** The Blender window stays open; the user watches the agent
  work. Headless is the same command core driven by `serve_blocking()`.
- **Scope = full 3D craft.** Model, sculpt, retopo, UV, shade (node graphs),
  texture/bake, modifiers, geometry nodes, constraints, rig, animate,
  physics/sim, light, render, scene, io. **Excludes** the non-3D editors (video
  sequencer, compositor, motion tracking, 2D grease-pencil illustration).

## 3. Architecture — three tiers, one router, one manifest

All capability is addressable through one `Router`, in three tiers distinguished
by a `tier` field on `ToolSpec`:

| Tier | Name | What | How built | Default exposure |
|------|------|------|-----------|------------------|
| 1 | **Craft verbs** | Few dozen senior-artist composite tools (`uv.smart_unwrap_and_pack`, `model.retopo_quads`, `bake.normals`) | Hand-built | Always exposed *(mostly layer 2 — deferred)* |
| 2 | **Domain catalogs** | Typed tools for the high-frequency native operators per craft area | **Generated** from the manifest | Lazy-loaded per domain |
| 3 | **Reflection floor** | `capabilities.search → describe → invoke` over live Blender RNA, with committed manifest/codegen drift checks | Live RNA at runtime + manifest offline | Always exposed |

### 3.1 The unifying manifest

A single generated artifact powers tiers 2 and 3.

- **Producer:** a script run *inside* Blender (`scripts/gen_manifest.py`) walks
  `bpy.ops` and `bpy.types` via RNA and emits
  `src/niua_blender_mcp/manifest/blender_5_1.json`: for every operator — idname,
  category, label, description, `poll`/context hints where derivable, and each
  property's id, type, enum items, default, hard min/max, array length,
  required/readonly. Plus a curated mapping of operator categories → craft
  domains and a "high-frequency" allowlist per domain (the tier-2 selection).
- **Version-stamped & committed.** The manifest header records the Blender
  version it was generated from. It is regenerated per Blender version and
  committed to the repo, so the server (which may run on a machine without
  Blender) reads it statically.
- **Consumer (tier 2):** a generator (`src/niua_blender_mcp/codegen/`) reads the
  manifest and emits typed `ToolSpec`s for the allowlisted operators, grouped by
  domain, tagged `tier="generated"`.
- **Consumer (tier 3):** runtime `capabilities.search`/`describe` use live RNA in
  the add-on, and `capabilities.invoke` delegates through the same validated
  `rna.call_operator` path. The committed manifest remains the offline catalog,
  tier-2 generator input, and drift-check fixture.

This is the key move: **one committed manifest plus a live-RNA reflection floor.**
Tier 2 is generated from the manifest; tier 3 stays accurate for the connected
Blender version by asking live RNA at runtime.

### 3.2 The `capabilities` meta-domain (discoverability front door)

The context-window constraint (cannot put thousands of tools in front of the
model) is solved by one always-present meta-domain:

- `capabilities.domains()` → the map: every craft domain + a coverage summary
  (tier-1 verb count, tier-2 generated count, tier-3 reachable count).
- `capabilities.search(query, kind?, domain?, limit?)` → ranked hits across
  **all three tiers** (a craft verb, a generated op, or a raw operator), matched
  over names + docs. The agent's "F3 operator search."
- `capabilities.describe(id)` → full typed schema for any capability id: params,
  enums, required mode/selection/poll, undo behavior, one example.
- `capabilities.invoke(id, args)` → validated, context-resolved, undo-safe
  dispatch. This *is* tier 3 (it supersedes/wraps `rna.call_operator`).

`search`/`describe` resolve against live RNA in the add-on, which avoids manifest
drift for the connected Blender process. The committed manifest is still used for
offline catalog tests and generated tier-2 specs.

### 3.3 Lazy loading

Default `tools/list` exposure = tier-1 craft verbs + `capabilities` +
`feedback`/`session`/`scene`/`io` essentials. Tier-2 generated domain catalogs
load on demand (per-domain) for hosts that support dynamic tool lists; on hosts
that do not, every tier-2/tier-3 capability remains reachable via
`capabilities.search`/`invoke`. The agent always has a small front door to an
unbounded surface. `Router.select(categories)` already supports this; the server
gains a "default set + on-demand domain load" policy on top of it.

## 4. How this maps onto existing code

This is an evolution, not a rewrite. Concretely:

- `kernel/contract.py` — add `tier: str = "curated"` to `ToolSpec` (values
  `curated`/`generated`/`reflection`). Keep `source` for back-compat or fold it
  into `tier` (plan decides). Add an `examples`/`undo` doc field if cheap.
- `kernel/router.py` — keep curated-wins precedence; generalize to a tier
  precedence (curated > generated > reflection). Add an index used by
  `capabilities.search` (name + summary + category + tier).
- `domains/introspection.py` + `domains/rna_exec.py` — refactored into / wrapped
  by the new `capabilities` domain. `rna.*` names kept as aliases initially so
  nothing breaks; `capabilities.*` is the canonical surface. The addon-side
  handlers stay (they hold the `bpy` logic); the manifest-backed validation is
  added server-side before dispatch.
- New: `scripts/gen_manifest.py` (producer, runs in Blender), `manifest/`
  (committed JSON), `codegen/` (manifest → generated `ToolSpec`s), `domains/`
  generated catalogs (or generated at import time from the manifest).
- Parity test (`tests/test_parity.py`) extended so generated tools also satisfy
  server-SPECS ↔ addon-COMMANDS parity (generated tools dispatch through the
  shared `capabilities.invoke`/`rna.call_operator` handler, so parity holds by
  routing, not by 1:1 handler pairs — the plan makes this explicit).

## 5. Non-goals (deferred, named, not built in this spec)

- **Layer 2 — the senior artist:** craft verbs (tier 1) + judgment *playbooks*
  (the "30 years" encoded as recipes + heuristics). Its own spec.
- **Deeper eyes:** topology-flow, UV-layout, texel-density, shading-error,
  silhouette, reference-match visualization. Co-designed with layer 2. (Note: the
  known `feedback.capture` WIREFRAME-renders-as-solid bug is a layer-2-era fix.)
- **Game pipeline:** LOD / collision / atlas / engine conventions.
- Non-3D editors (VSE, compositor, motion tracking, 2D GP) — out of scope
  entirely.

## 6. Milestones (layer 1)

1. **Manifest + tiered router.** `gen_manifest.py`, committed manifest, `tier`
   metadata, tier precedence, and live-RNA tier-3 runtime validation.
2. **`capabilities` front door.** `domains/search/describe/invoke` + lazy
   loading; agent can find and run anything. `rna.*` kept as aliases.
3. **Tier-2 generator.** Manifest → generated catalogs; first wave of domains
   (modeling, UV, shading, modifiers).
4. **Coverage fill.** Remaining full-3D-craft domains get tier-2 catalogs; tier 3
   already covers the tail.

## 7. Success criteria

- **Completeness:** every in-scope operator exposed by live Blender RNA is reachable
  through `capabilities`, with committed-manifest drift checks covering sampled
  Blender 5.1.x operators.
- **Correctness:** every invocation is context-resolved, poll-checked, and
  undo-safe; server↔addon parity holds for curated *and* generated tools.
- **Discoverability:** for a battery of "describe-the-task" prompts, the agent
  finds the right capability via `capabilities.search` without `execute_python`.
- **North-star eval (drives layer 2):** a **senior task battery** — game-ready
  prop with clean quad topology; UV unwrap at target texel density; bake normals
  high→low; layered PBR material; basic rig — each scored by objective metrics +
  visual critique.

## 8. Risks & mitigations

- **Manifest drift vs. live Blender.** Mitigate: version-stamp; a test that
  re-derives a sample of the manifest from live RNA and asserts it matches; live
  fallback in `describe`/`invoke`.
- **Tier-2 surface bloat.** Mitigate: tier-2 is an explicit per-domain
  allowlist, not "every operator"; the long tail lives in tier 3.
- **POINTER/COLLECTION operator args** (datablock references) are still
  unsupported by the generic coercer. Mitigate: document the limit; tier-1 craft
  verbs handle the cases that need datablock wiring; consider a name→datablock
  resolver in a later milestone.
- **Host without dynamic tool lists.** Mitigate: full surface always reachable
  via `capabilities.search`/`invoke`; tier-2 is an ergonomic bonus, not a
  dependency.
