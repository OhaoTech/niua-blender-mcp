# niua Blender MCP — Design

Status: APPROVED (architecture). Date: 2026-06-19.

## 1. Vision

An **agentic Blender**: a Model Context Protocol server that lets an AI agent drive a
live Blender the way a top-tier technical artist does — modeling, UV, shading,
animation, rigging, rendering, everything. Not a thin remote-control toy and not a
fixed list of hand-written tools. "A new way to use Blender."

The Blender window stays **open and visible**. The user watches the agent work in real
time, can intervene, and can `Ctrl+Z` any single agent action. Headless operation
(`blender --background`) is the same core with no window attached, added later.

## 2. Context and boundaries

This MCP is one stage of niua's agentic game-creation toolchain, but it is **fully
standalone and decoupled**:

- **niua MCP** (remote/hosted) generates assets. Its output is a *file*.
- **Blender MCP** (this repo) is a standalone agentic Blender. It has **zero knowledge
  of niua**. niua's asset files are ordinary inputs consumed through the generic `io`
  (import) domain. Integration lives one level up, at the orchestrating agent, which
  holds all three MCPs and routes niua output into Blender import. This MCP is reusable
  outside niua entirely.
- A downstream engine/export MCP can consume Blender's exported files. That integration
  remains decoupled and outside this repo.

**Competitive landscape.** `youichi-uda/blender-mcp-pro` ($5/mo, 120+ hand-written
tools, visible GUI, main-thread execution) already covers raw Blender features well. We
do **not** compete on tool count. We win on (a) a source/RNA-introspection engine that
outscales any hand-written list and auto-tracks the running Blender version, (b) a
clean kernel that stays maintainable at 200+ tools, and (c) being a free, embeddable
piece of niua's owned end-to-end loop.

## 3. Principles

1. Build the hard part (the kernel) once; everything else is a pluggable pack.
2. One tool defined once (the manifest contract); both processes and all capability
   layers honor it.
3. `bpy` only ever runs on Blender's main thread.
4. Coverage is not capped by labor: curated tools + RNA generation + escape hatch.
5. Every mutation is one undo step: safe rollback and a natural human `Ctrl+Z`.
6. Feedback is opt-in and two-channel: analytic numbers for facts, images for taste.

## 4. Macro architecture: Kernel + Domain Packs

Two ideas composed. **Horizontal layers** (every request flows down the same stack) and
**vertical domains** (self-registering subsystems). **Routing is the seam.**

```
                     ┌──────────── DOMAIN PACKS (vertical, pluggable) ────────────┐
                     │ scene │ mesh │ uv │ shading │ modifiers │ anim │ rig │ io   │
 ┌───────────────────┼───────┴──────┴────┴─────────┴───────────┴──────┴─────┴──────┤
L5 Cross-cutting svcs │ validation · error model · undo/transaction · log · feedback│
L4 Capability         │ RNA introspection · manifest generation · lazy categories   │
L3 Domain handlers    │ the bpy operations, grouped per column                      │
L2 Routing / dispatch │ tool-name → handler registry  (the spine)                   │
L1 Transport          │ MCP stdio (server) ◄── manifest contract ──► socket (addon) │
 └───────────────────────────────────────────────────────────────────────────────┘
     SERVER PROCESS (Python)        │ JSON over TCP │      ADDON PROCESS (Python, in Blender)
                                    ▼               ▼
                       main-thread queue (bpy.app.timers) → runs L3 on Blender's main thread
```

**The Kernel** (small, stable, built once): transport, router, main-thread queue,
manifest machinery, RNA introspection, context resolver, and cross-cutting services
(validation, error model, undo/transaction, logging, feedback).

**Domain Packs** (added forever): `scene, mesh, uv, shading, modifiers, anim, rig, io`,
and more. Each is a folder that self-registers with the router. The kernel never changes
when a pack is added.

## 5. The contract: ToolSpec

One manifest entry per tool, honored by both processes.

```python
ToolSpec(
    name="uv.smart_unwrap",
    category="uv",                 # lazy-loading group
    summary="Angle-based UV unwrap of a mesh object",
    params={
        "object": Str(required=True),
        "angle_limit": Float(default=66.0, min=1, max=89),
        "island_margin": Float(default=0.02),
    },
    command="uv.smart_unwrap",     # wire identifier
    mutates=True,                  # kernel wraps in an undo step
    feedback="uv_layout",          # kernel attaches a capture (opt-in)
    source="curated",              # curated | rna  (curated wins on collision)
)
```

The server turns a ToolSpec into an MCP tool + bridge call; the addon maps `command` to
a handler. Change once, both sides move.

## 6. Domain pack anatomy

```
domains/<name>/
  manifest.py   # the ToolSpecs
  handlers.py   # bpy code, one function per command, runs on main thread, pre-validated
  __init__.py   # register(router): router.add(MANIFEST, HANDLERS)
```

Handlers stay tiny because the kernel wraps every call:

```
request → validate(spec) → enqueue to main thread
        → open undo step (if mutates) → run handler → capture feedback (if set)
        → commit / rollback → uniform result or structured error → agent
```

## 7. Kernel internals

### 7.1 Transport
- Server: MCP **stdio** via the official MCP Python SDK (tool registration +
  `list_changed` lazy-loading for free).
- Addon: a **plain TCP socket**, newline-delimited JSON, on `127.0.0.1` (configurable).
- Bridge messages: `{"command": str, "payload": {...}}` → `{"ok": bool, "result"|"error"}`.

### 7.2 Main-thread queue (the heartbeat)
`bpy` is main-thread-only; the socket server runs on a background thread. The socket
thread only **enqueues**; a `bpy.app.timers`-registered callback drains the queue on the
**main thread**, runs the handler, and signals the waiting socket thread via an Event.

```python
_REQUESTS = queue.Queue()                       # (command, payload, box)

def handle_request(command, payload, timeout=30.0):   # background socket thread
    box = _Box(); _REQUESTS.put((command, payload, box))
    if not box.event.wait(timeout):
        return {"ok": False, "error": {"code": "timeout", "message": f"{command} > {timeout}s"}}
    return {"ok": False, "error": box.error} if box.error else {"ok": True, "result": box.value}

def _drain():                                          # MAIN THREAD via timer
    while True:
        try: command, payload, box = _REQUESTS.get_nowait()
        except queue.Empty: break
        try:    box.value = dispatch_on_main(command, payload)   # bpy runs here, safely
        except Exception as exc:
            box.error = {"code":"handler_error","message":str(exc),"traceback":traceback.format_exc()}
        finally: box.event.set()
    return 0.02                                        # re-poll in 20ms

def register():
    start_socket_server(handle_request)
    bpy.app.timers.register(_drain, persistent=True)
```

Single consumer = **serialized FIFO execution**. One scene, one editor, no locks needed.

### 7.3 Undo / transaction
Every mutating call is wrapped in one Blender undo step. Failure rolls back. Success
leaves exactly one undo step, so the watching human can `Ctrl+Z` any single agent action.

```python
def dispatch_on_main(command, payload):
    spec = ROUTER.spec(command); args = validate(spec, payload)
    if not spec.mutates: return ROUTER.handler(command)(CTX, **args)
    bpy.ops.ed.undo_push(message=f"niua:{spec.name}")
    try: result = ROUTER.handler(command)(CTX, **args)
    except Exception:
        try: bpy.ops.ed.undo()
        except Exception: pass
        raise
    if spec.feedback: result["_feedback"] = capture(spec.feedback)
    return result
```

### 7.4 Error model + timeouts (two-sided)
Uniform structured errors `{code, message, detail?}`. Server-side socket read timeout is
set slightly longer than the addon op timeout. Frozen/dead Blender → server returns a
transport error so the agent is never left hanging. Handler exception → rollback +
structured error, **Blender survives**. Blender process death → socket drop → connection
error + reconnect path. N-panel shows live server state.

### 7.5 Context resolver (make-or-break for generated tools)
RNA gives a tool's parameters but not the context an operator needs (edit mode, active
object, selection, area type). The kernel checks `op.poll()` first (clean
"preconditions not met" on failure) and wraps execution in a context manager that sets
up mode/area/`temp_override`/selection and restores it. Handlers never deal with context.

```python
with ctx.ensure(active=obj, mode='EDIT', area='VIEW_3D', select=selection):
    bpy.ops.mesh.bevel(**args)
```

## 8. Capability surface: three sources of router entries

1. **Curated tools** — hand-written ToolSpecs for the hot path. Highest quality.
2. **RNA-generated tools** — mined from Blender's API (see §9). Scales breadth mechanically.
3. **`execute_python`** — gated escape hatch for the last 1%.

All three dispatch through the same pipeline (validation, main-thread, undo, feedback).

### 8.1 Three-tier capability surface (Layer 1)

The current Layer 1 surface turns Blender's broad API into a small always-visible
front door plus a complete validated floor:

1. **Craft verbs (`tier="curated"`)** — hand-written, high-signal tools for common
   technical-artist workflows. These win on name collision and are always exposed.
2. **Domain catalogs (`tier="generated"`)** — typed `ToolSpec`s generated from the
   committed manifest for allowlisted high-frequency native operators. Generated
   tools are callable by name, but hidden from `tools/list` by default to avoid
   flooding the context window. Set `NIUA_BLENDER_MCP_LIST_ALL=1` to list them.
3. **Reflection floor (`tier="reflection"`)** — `capabilities.domains`,
   `capabilities.search`, `capabilities.describe`, and `capabilities.invoke`.
   This is always exposed and is the agent's F3-style search/describe/invoke path
   for the full live Blender operator surface.

The unifying artifact is `src/niua_blender_mcp/manifest/blender_5_1.json`,
generated inside Blender by `scripts/gen_manifest.py` and committed. The manifest
is version-stamped, read offline by `niua_blender_mcp.manifest`, and consumed by
`niua_blender_mcp.codegen` to emit tier-2 specs. Runtime `capabilities.search` and
`capabilities.describe` delegate to live RNA in the add-on so results match the
running Blender; the manifest drives code generation and drift checks.

## 9. RNA introspection engine ("built on the source")

Blender exposes its whole API at runtime via RNA, with the same metadata it uses for its
own tooltips. We mine operators (`bpy.ops.<cat>.<op>.get_rna_type()`) and data properties
(`bpy.types.<Type>.bl_rna.properties`): identifier, description, type, default,
hard/soft min/max, enum choices, required.

Three products:
- **`rna.describe(path)`** — live, on-demand discovery for the agent. Never stale.
- **Generated ToolSpecs** — a registration pass mines allowlisted categories and emits
  curated-quality specs (Blender's own help text becomes the descriptions).
- **`rna.call_operator(idname, args)` / `rna.set_property(path, value)`** — generic
  structured execution for anything not pre-generated.

Curation gate: allowlist TA categories (`mesh, object, uv, material, sculpt, curve,
armature, pose, anim, nla, graph, transform, node, geometry_nodes, …`); denylist
`wm, screen, file, ui, console, preferences` and internal panels; quality filter
(require description, drop pointer/collection-heavy ops and deprecated); tag
`source="rna"` so a `source="curated"` spec wins on name collision.

Structural wins: free high-quality descriptions, auto-tracks the running Blender version
(regenerates on a 5.0 jump instead of rotting), coverage uncapped by labor.

## 10. Feedback subsystem ("the eyes")

Two channels:
- **Analytic** — structured numbers (tris, n-gons, non-manifold count, UV overlap %,
  texel density, bbox dims). Best signal for checkable facts.
- **Visual** — images for aesthetic judgment.

Capture modes: viewport snapshot, **multi-angle/turntable** (front/3-4/side/top — the
anti-blob), UV layout, shaded render, topology/wireframe, diagnostic overlays.

Mechanism: a **dedicated capture camera** + `bpy.ops.render.opengl(write_still=True)`
(fast workbench render) so the user's viewport never moves. Upgrade path to
`gpu.types.GPUOffScreen` for zero-disturbance later. Images returned as native MCP image
content (base64 PNG). Feedback is **opt-in per tool** with a resolution cap (768px) due
to image token cost.

Quality loop (the moat, designed-for not built-now): because the agent is multimodal,
the first critic is the agent itself — `do op → capture multi-angle → agent looks →
agent adjusts`. The kernel only must make seeing cheap and faithful; the autonomous loop
is later, no architecture change. The very original problem (text-to-realistic-model
produces blobs) is addressed here: deliberate ops + faithful multi-angle eyes + an
iterating agent, instead of blind one-shot generation.

## 11. Locked decisions

- Server language: **Python** (best-of-breed per MCP). Add-on: Python (bpy).
- **Visible GUI first**; headless is the same core later.
- Transport: **TCP socket, newline-delimited JSON**.
- Main-thread execution via **`bpy.app.timers` queue**; serialized FIFO.
- One undo step per mutation.
- Capability = curated + RNA-generated + gated `execute_python`.
- **No `vendor/blender` submodule** (runtime RNA beats static C source for the agent).
- Manifest ToolSpec is the single cross-bridge contract.

## 12. Deferred / open

- Async heavy ops (modal operators for long render/bake without UI freeze).
- `GPUOffScreen` non-intrusive capture.
- Autonomous critique loop + optional dedicated critic model.
- Headless worker mode and a worker pool for niua's backend.
- POINTER/COLLECTION operator params (need name→datablock resolution).

## 13. Repo structure

```
niua-blender-mcp/
  pyproject.toml, README.md, docs/{DESIGN.md,PLAN.md}
  src/niua_blender_mcp/
    __main__.py        stdio entry
    server.py          MCP server, tool registration, lazy categories
    bridge.py          TCP client to the add-on
    kernel/            contract (ToolSpec), router, validation, errors
    domains/           server-side manifests mirrored from the addon
  blender_addon/niua_mcp_bridge/
    __init__.py        N-panel + socket server + main-thread queue + dispatch
    kernel/            queue, undo/transaction, context resolver, feedback, introspection
    domains/           scene, mesh, uv, shading, modifiers, anim, rig, io (added over time)
  tests/               fake-bpy unit tests + a headless smoke test
```

## 14. Phase plan

- **Phase 0 — the Kernel + proof.** Package skeleton, MCP server (stdio), addon with
  N-panel Start/Stop, TCP socket, main-thread queue + undo, router + ToolSpec contract,
  validation + error model, and just enough to prove the spine end to end:
  - `scene` domain: `scene_info` (read), `create_object` + `set_transform` (main-thread,
    undoable writes).
  - `rna.describe` (introspection primitive).
  - `feedback.capture` (single viewport snapshot returned as MCP image).
  - gated `execute_python`.
  - **Done = in a live Blender window, the agent reads the scene, creates and moves an
    object, gets a screenshot back, the human can `Ctrl+Z` it, and a bad call returns a
    clean error without crashing Blender.** TDD with fake-bpy + one headless smoke test.
- **Phase 1+ — domain depth, one pack at a time:** mesh edit → uv → shading/nodes →
  modifiers → animation → rigging. Each adds a folder; kernel untouched.
- **Phase 2 of capability — RNA generation pass** over allowlisted categories, plus the
  context resolver hardening.
- **Phase 3 — feedback depth:** multi-angle/turntable, UV/topology/diagnostic captures.
- **Phase N — engine-neutral file seams (`io`) + headless mode + the critique loop.**
```

## Phase 6 — the critique loop

The original problem was blind one-shot text-to-model producing blobs: a single
generation step with no perceptual feedback. The answer is deliberate ops + faithful
multi-angle eyes + an **iterating agent**. This phase ships the two *primitives* that make
that iteration tight. **The critic is the agent itself** — it is multimodal, so it looks
at the renders and reads the numbers and decides. The MCP does **not** run an autonomous
loop in Python; it supplies a cheap, faithful **observe** and a robust **safe-iterate**.

**The two primitives.**

- `feedback.critique` — the one OBSERVE call. Returns a single bundle:
  `{ available, images:[…multi-angle…], report:{…mesh.report…}, uv:{…uv.report|null} }`.
  Images give *taste* signal (silhouette, proportion, the anti-blob multi-angle view);
  the report gives *checkable facts* (tris, n-gons, non-manifold edges, bbox dims,
  UV/material counts). One round-trip, both channels. Read-only; degrades to
  `available:false` images on a headless box while the analytic report still returns.
- `session.checkpoint` / `session.revert` / `session.list_checkpoints` — SAFE-ITERATE
  beyond Blender's single-op undo. `checkpoint` snapshots the object's data + transform
  into a dedicated store (a non-destructive `obj.data.copy()`, so it does not mutate the
  visible scene); `revert` swaps a fresh copy of that snapshot back (one undo step);
  it is independent of Blender's fragile, human-shared undo stack, so a multi-step edit
  that turned out worse can be rolled back cleanly.

**The agent-side recipe (the loop the agent drives, not the server):**

```
session.checkpoint(object)            # save a known-good state
  → make an edit (mesh.* / sculpt.* / modifiers.* / rna.call_operator / …)
  → feedback.critique(object)         # observe: multi-angle images + report + uv
  → the agent JUDGES: silhouette & proportion from the images, topology &
     n-gons & non-manifold & bbox from the report, layout from uv
  → keep it (and checkpoint again as the new baseline)
     OR session.revert(object)        # undo the regression, try a different edit
  → repeat until the form is right
```

This is the moat from §10 made operational: seeing is cheap and faithful, rolling back is
safe, and the iterating multimodal agent closes the gap that one-shot generation can't.
An optional dedicated critic model and a fully autonomous (no-human-in-loop) variant are
still deferred (§12) and need no architecture change — they reuse these same primitives.
