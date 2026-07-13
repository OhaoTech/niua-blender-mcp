# Retopo-to-Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a curated `object.retopo` tool (voxel-remesh → quadriflow-to-budget) and use it instead of decimate in `bake_and_finish`, so the 2 densest assets get a clean, bakeable low-poly and cross the surface-fidelity floor.

**Architecture:** `object.retopo` is a generic interface-layer Blender op (both sides + SDK); `bake_and_finish`'s `_bake_transfer` move swaps decimate for it (policy). The `surface_fidelity` ruler grades the result — no new metric. `make_game_ready` (skill #1) is untouched.

**Tech Stack:** The hand-rolled MCP kernel + TCP bridge; Blender 5.1 `object.voxel_remesh` + `object.quadriflow_remesh`; pytest; Blender for the LIVE acceptance.

## Global Constraints

- **ZERO niua knowledge.** `object.retopo` is a generic remesh op; only the skill move is policy.
- **Parity green** (both sides gain `object.retopo` in one commit); **SDK drift green** (regenerate so `session.object.retopo` exists); **layer boundary green**.
- **`make_game_ready` (skill #1) + its benchmark reading unchanged** — this only touches `bake_and_finish` (skill #2).
- **Blender remesh API facts (verified against the manifest):** `object.voxel_remesh` takes NO op args — set `obj.data.remesh_voxel_size` (and optionally `remesh_voxel_adaptivity`) on the mesh, then invoke `bpy.ops.object.voxel_remesh()`. `object.quadriflow_remesh` params: `mode` (ENUM: FACES/EDGES/RATIO), `target_faces` (INT), `mesh_area`, `seed`, `smooth_normals`, `use_preserve_sharp`, `use_preserve_boundary`, `use_mesh_symmetry`, `preserve_attributes`, `target_edge_length`, `target_ratio`.
- **No silent decimate fallback:** if either remesh step fails, `object.retopo` raises a structured error; the skill move then reverts (honest decline), never falls back to decimate.
- **Budget units:** the asset-class budget is in TRIANGLES; quadriflow targets FACES (quads ≈ tris/2), so the skill passes `target_faces = max(1, budget // 2)`.
- **Full offline suite green before every commit:** `NIUA_SKIP_BLENDER=1 python -m pytest -q` (currently 819 passed, 71 skipped).
- **Commit style:** one commit per task, conventional subject, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `object.retopo` tool (both sides + SDK)

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/objects.py` (Command + handler)
- Modify: `src/niua_blender_mcp/domains/objects.py` (ToolSpec)
- Regenerate: `src/niua_blender_mcp/client/tools/object.py`
- Test: `tests/domains/test_retopo.py`

**Interfaces:**
- Produces tool `object.retopo`, `mutates=True`, `timeout_tier="heavy"`, params:
  `object: Str(required)`, `target_faces: Int(required, minimum=1)`, `voxel_size: Float(default=0.0, minimum=0.0)` (0 = auto from bbox), `adaptivity: Float(default=0.0, minimum=0.0, maximum=1.0)`, `preserve_sharp: Bool(default=True)`, `preserve_boundary: Bool(default=True)`.
  Handler: set voxel size (auto = longest bbox axis / 128 when `voxel_size<=0`), `object.voxel_remesh`, then `object.quadriflow_remesh(mode="FACES", target_faces=…)`; returns `{object, faces, tris}`.

- [ ] **Step 1: Write the failing offline tests**

Create `tests/domains/test_retopo.py`:

```python
def test_retopo_registered_both_sides_with_parity():
    from niua_blender_mcp.domains import build_router
    from niua_mcp_bridge.domains import build_default_registry
    server = {s.command for s in build_router().specs()}
    addon = build_default_registry().names()
    assert "object.retopo" in server
    assert "object.retopo" in addon


def test_retopo_spec_is_heavy_mutating_with_expected_params():
    from niua_blender_mcp.domains import build_router
    spec = next(s for s in build_router().specs() if s.name == "object.retopo")
    assert spec.mutates is True
    assert spec.timeout_tier == "heavy"
    assert {"object", "target_faces"} <= set(spec.params)


def test_sdk_exposes_retopo_after_regen():
    from niua_blender_mcp.client import ToolSession
    session = ToolSession(bridge=None)
    assert hasattr(session.object, "retopo")
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_retopo.py -q`
Expected: FAIL — tool not registered.

- [ ] **Step 3: Add the addon handler + Command**

Read the existing `bake_transfer`/`lod_create` handlers in `blender_addon/niua_mcp_bridge/domains/objects.py` first, and match their `ctx.ensure` + error-import conventions. Add:

```python
def retopo(ctx: Ctx, payload: dict) -> dict:
    """Retopologize an object to a clean quad mesh at a face budget: voxel remesh (robust
    cleanup -> watertight manifold) then quadriflow to target_faces. No decimate fallback --
    fails cleanly if either remesh step fails.
    """
    bpy = ctx.bpy
    obj = ctx.get_object(payload.get("object", ""))
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(INVALID_PARAMS, "retopo target must be a mesh")
    target_faces = int(payload.get("target_faces", 0))
    if target_faces < 1:
        raise BridgeError(INVALID_PARAMS, "target_faces must be >= 1")
    voxel_size = float(payload.get("voxel_size", 0.0))
    adaptivity = float(payload.get("adaptivity", 0.0))
    preserve_sharp = bool(payload.get("preserve_sharp", True))
    preserve_boundary = bool(payload.get("preserve_boundary", True))
    if voxel_size <= 0.0:
        dims = list(getattr(obj, "dimensions", (0.0, 0.0, 0.0)))
        longest = max(dims) if dims and max(dims) > 0 else 1.0
        voxel_size = longest / 128.0
    try:
        with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
            mesh = obj.data
            mesh.remesh_voxel_size = voxel_size
            if hasattr(mesh, "remesh_voxel_adaptivity"):
                mesh.remesh_voxel_adaptivity = adaptivity
            ctx.check_poll(bpy.ops.object.voxel_remesh)
            bpy.ops.object.voxel_remesh()
            ctx.check_poll(bpy.ops.object.quadriflow_remesh)
            bpy.ops.object.quadriflow_remesh(
                mode="FACES", target_faces=target_faces,
                use_preserve_sharp=preserve_sharp, use_preserve_boundary=preserve_boundary,
                smooth_normals=True,
            )
    except RuntimeError as exc:
        raise BridgeError(PRECONDITION, f"retopo failed: {exc}") from exc
    m = obj.data
    faces = len(m.polygons)
    tris = sum((len(p.vertices) - 2) for p in m.polygons)
    return {"object": obj.name, "faces": faces, "tris": tris}
```

Register: `Command("object.retopo", retopo, mutates=True, feedback="viewport")` in COMMANDS. Ensure `INVALID_PARAMS, PRECONDITION, BridgeError` are imported in objects.py (they already are for `bake_transfer`).

- [ ] **Step 4: Add the server ToolSpec** in `src/niua_blender_mcp/domains/objects.py` SPECS:

```python
ToolSpec(
    name="object.retopo", category="object",
    summary="Retopologize a mesh to clean quads at a face budget (voxel remesh -> quadriflow)",
    command="object.retopo",
    params={
        "object": Str(required=True, summary="Mesh object to retopologize"),
        "target_faces": Int(required=True, minimum=1, summary="Target quad face count"),
        "voxel_size": Float(default=0.0, minimum=0.0, summary="Voxel size for the cleanup pass; 0 = auto from bbox"),
        "adaptivity": Float(default=0.0, minimum=0.0, maximum=1.0, summary="Voxel adaptivity (0 = uniform)"),
        "preserve_sharp": Bool(default=True, summary="Preserve sharp edges in quadriflow"),
        "preserve_boundary": Bool(default=True, summary="Preserve open boundaries in quadriflow"),
    },
    mutates=True, feedback="viewport", timeout_tier="heavy",
),
```

- [ ] **Step 5: Regenerate the SDK**

```bash
cat > /tmp/gen_sdk.py <<'PY'
from pathlib import Path
from niua_blender_mcp.client import generate
out = Path("src/niua_blender_mcp/client/tools")
for domain, source in generate.generate_all().items():
    (out / f"{domain}.py").write_text(source, encoding="utf-8")
PY
NIUA_SKIP_BLENDER=1 python /tmp/gen_sdk.py && rm /tmp/gen_sdk.py
```

- [ ] **Step 6: Run tests + parity + drift + full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_retopo.py tests/test_parity.py tests/test_client_sdk.py -q && NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/objects.py src/niua_blender_mcp/domains/objects.py src/niua_blender_mcp/client/tools/object.py tests/domains/test_retopo.py
git commit -m "feat: object.retopo — voxel-remesh -> quadriflow-to-budget (both sides + SDK)"
```

---

### Task 2: `bake_and_finish` uses retopo instead of decimate

**Files:**
- Modify: `src/niua_blender_mcp/finishing/skills/bake_and_finish.py`
- Test: `tests/test_skills.py` (extend)

**Interfaces:**
- Consumes: `session.object.retopo(object, target_faces, ...)`; the existing `feedback.quality` budget read.
- Produces: `_bake_transfer` calls `object.retopo` (not the decimate modifier chain); `TOOLS_USED` gains `object.retopo` (and no longer needs `modifiers.add/set/apply` *unless still used elsewhere in the skill — check and keep any still-referenced*).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_skills.py` (reuse the `FidelityBridge`/`FakeBridge` harness; extend it to record `object.retopo` calls):

```python
def test_bake_transfer_uses_retopo_not_decimate():
    from niua_blender_mcp.client import ToolSession
    from niua_blender_mcp.finishing.skills import bake_and_finish
    # readiness marks the triangle-budget gate failing so the bake move fires
    bridge = FidelityBridge(before=_readiness(0.4, ["engine.within_triangle_budget"]),
                            effects={"object.bake_transfer": _readiness(0.6)}, fidelity_after=0.9)
    session = ToolSession(bridge)
    bake_and_finish.run(session, "subject", {"asset_class": "hard_surface_prop"})
    tools = [c[0] for c in bridge.calls]
    assert "object.retopo" in tools
    assert "modifiers.add" not in tools  # decimate path is gone from the bake move
    # target_faces derived from the budget (5000 tris in the fake quality) -> ~2500 faces
    retopo_call = next(c for c in bridge.calls if c[0] == "object.retopo")
    assert retopo_call[1]["target_faces"] == 2500


def test_retopo_in_tools_used_and_registered():
    from niua_blender_mcp.domains import build_router
    from niua_blender_mcp.finishing.skills import bake_and_finish
    assert "object.retopo" in bake_and_finish.TOOLS_USED
    known = {("capabilities.invoke" if s.tier == "generated" else s.command) for s in build_router().specs()}
    assert bake_and_finish.TOOLS_USED <= known
```

(Ensure the FakeBridge's `feedback.quality` stub returns `{"topology": {"tris": 100000}, "asset_class": {"effective_defaults": {"triangle_budget": 5000}}}` so budget//2 = 2500. If the harness in this file uses a different quality stub, align the expected number to it.)

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_skills.py -q`
Expected: FAIL — the move still uses the decimate modifier chain.

- [ ] **Step 3: Amend `_bake_transfer` in `bake_and_finish.py`**

Read the current `_bake_transfer`. Replace the decimate block (`modifiers.add/set/apply`) with a retopo call; keep the duplicate-high / unwrap / bake / delete-high structure:

```python
def _bake_transfer(session, subject, info):
    high = f"{subject}__high"
    session.object.duplicate(object=subject, name=high)   # keep the pre-retopo detail as bake source
    q = session.feedback.quality(object=subject, asset_class=info["asset_class"])
    budget = int(q.get("asset_class", {}).get("effective_defaults", {}).get("triangle_budget") or 0)
    tris = int(q.get("topology", {}).get("tris") or 0)
    if budget > 0 and (tris <= 0 or budget < tris):
        target_faces = max(1, budget // 2)   # budget is in tris; quadriflow targets quad FACES
        session.object.retopo(object=subject, target_faces=target_faces)
    session.mesh.select_all(object=subject, action="SELECT")
    session.uv.smart_unwrap(object=subject)
    session.uv.pack_islands(object=subject)
    session.object.bake_transfer(source=high, target=subject, maps="NORMAL,AO")
    session.object.delete(objects=high)
```

Update `TOOLS_USED`: add `"object.retopo"`; remove `"modifiers.add"`, `"modifiers.set"`, `"modifiers.apply"` **only if no other move in the skill uses them** (grep the file — if another move does, keep them). Keep `object.duplicate`, `object.bake_transfer`, the uv/mesh tools.

- [ ] **Step 4: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_skills.py -q`
Expected: PASS. `make_game_ready` tests unchanged.

- [ ] **Step 5: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add src/niua_blender_mcp/finishing/skills/bake_and_finish.py tests/test_skills.py
git commit -m "feat: bake_and_finish retopos to budget (voxel->quadriflow) instead of decimating"
```

---

### Task 3: LIVE acceptance — the densest assets cross the floor

**Files:**
- Create: `docs/reports/retopo-bake-run.md`

- [ ] **Step 1: Launch Blender with the new addon**

```bash
pkill -f blender_supervise.py || true; pkill -x blender || true
```
Then (separate command, background): `python scripts/blender_supervise.py --port 8765`; wait for the bridge (bash tcp probe on 127.0.0.1:8765). Verify `object.retopo` is live: `python scripts/bridge_call.py 8765 capabilities.tools '{"domain":"object"}'` should list `retopo`. (If the bridge answers in <5s, a stale Blender may be serving old code — hard-restart and confirm `retopo` is present before trusting any number.)

- [ ] **Step 2: Run bake_and_finish on all 5 assets**

Run: `python scripts/run_skill.py --skill bake_and_finish --outdir /tmp/niua_retopo_run`
Expected: completes; per-item `surface_fidelity` in the output. Compare against the decimate-era numbers (real_character 0.28, real_prop 0.34; the 3 good ones 0.82–0.90).

- [ ] **Step 3: Assess honestly**

Success = the 2 densest assets score **materially higher** than their decimate numbers, ideally ≥ 0.60 (KEPT to budget). The 3 previously-good assets must NOT regress (still ≥ 0.60, still to budget). If the samurai still can't cross 0.60 at its tight hard-surface budget, that's an honest finding (budget vs silhouette) — record the number and note whether a larger budget or a per-class retopo tweak would close it; do NOT lower the floor to force a pass.

- [ ] **Step 4: Capture before/after + write the report**

Render before/after captures of the 2 densest assets under retopo-bake (reuse the eyeball/gallery approach). Create `docs/reports/retopo-bake-run.md`: per-asset table (tris after, silhouette, surface_fidelity: decimate-era vs retopo-era, KEPT/REVERTED), the before/after images, and a plain statement of how many of 5 now reach budget at good fidelity. Note any asset still short and why.

- [ ] **Step 5: Commit**

```bash
git add docs/reports/retopo-bake-run.md
git commit -m "docs: retopo-bake run — densest assets to budget at good fidelity (or honest shortfall)"
```

---

## Self-Review

1. **Spec coverage:** `object.retopo` voxel→quadriflow both sides + SDK (Task 1) ✓; fails cleanly, no decimate fallback (Task 1 handler) ✓; `bake_and_finish` uses it instead of decimate (Task 2) ✓; `make_game_ready` untouched (Task 2 only edits bake_and_finish) ✓; ruler grades it, no new metric (Task 3 uses surface_fidelity) ✓; LIVE acceptance with honest shortfall reporting (Task 3) ✓; parity/boundary/drift (Task 1 Step 6) ✓.
2. **Placeholder scan:** the handler code uses the real verified API (voxel_size via `mesh.remesh_voxel_size`; quadriflow `mode="FACES"`+`target_faces`); no TBDs; the "check if modifiers.* still used" instruction is a concrete grep, not a deferral.
3. **Type consistency:** `object.retopo` params identical across addon handler (Task 1 Step 3), server spec (Task 1 Step 4), and skill call (Task 2 Step 3: `object=`, `target_faces=`); `target_faces = budget // 2` consistent between the skill code and the Task 2 test's expected 2500; returns `{object, faces, tris}` used only informationally.
