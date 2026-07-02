# Layer 2 Phase 1 — Form Perception (silhouette eye) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Give the agent a clean *form read* — a `feedback.silhouette` eye that renders a flat
high-contrast silhouette from a preset of angles and returns the existing proportion/symmetry
analytics alongside — because the altimeter baseline showed **silhouette is the weakest lens
(3.79)** and the pipeline cannot see form well.

**Architecture:** A new read-only eye that mirrors the proven `core/overlay.py` topology pattern:
snapshot the object's materials → assign a single flat EMISSION fill → render each preset view
through EEVEE (`_render_to_b64(..., "MATERIAL", ...)`) → restore. EEVEE-emission is used
deliberately: `render.opengl(view_context=False)` ignores Workbench shading (the gray-clay bug),
but honors emission materials. Framing reuses `core/capture.py`. The handler folds in the
existing `_proportion(obj)` and `_symmetry(mesh)` from the feedback module so one call returns
images **and** numbers.

**Tech Stack:** Python 3.14, pytest, recording fake-bpy for unit tests, real-Blender headless
smoke for the graceful-degrade envelope; live GL verification deferred to the altimeter re-run.

## Global Constraints

- Standalone repo — zero niua/Godot references.
- `from __future__ import annotations` atop every new `.py`.
- Read-only tool: `mutates=False`. It snapshots and **restores** materials + `material_index`
  exactly (the object must be byte-identical after the call).
- `bpy` only via the passed `bpy`/`ctx.bpy`; `import mathutils` directly if needed (never `bpy.mathutils`).
- Render through EEVEE emission (`_render_to_b64(bpy, cam, "MATERIAL", res)`) — do NOT use
  Workbench "SOLID"/"WIREFRAME" for the silhouette (render.opengl ignores it).
- Server `SPECS` ↔ add-on `COMMANDS` parity is enforced by `tests/test_parity.py`; register on both sides.
- Reuse `core/capture.py` framing (`PRESETS`, `view_camera`, `orbit_camera`, `_ensure_capture_camera`,
  `_apply_frame`, `_render_to_b64`, `scene_bbox`) and the feedback module's `_proportion`/`_symmetry`.
  Do NOT duplicate framing, render, or metric logic.
- Graceful degrade: any failure (headless/no-GPU) returns `{"available": False, "reason": str}`.

---

## File Structure

- Create: `blender_addon/niua_mcp_bridge/core/silhouette.py` — the render logic (mirror `core/overlay.py`).
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py` — add the `feedback.silhouette` handler + register in `COMMANDS`.
- Modify: `src/niua_blender_mcp/domains/feedback.py` — add the `feedback.silhouette` `ToolSpec` to `SPECS`.
- Create: `tests/core/test_silhouette.py` — fake-bpy unit tests for the core render/restore logic.
- Modify: `tests/test_smoke_headless.py` — add the graceful-degrade envelope test.

---

## Task 1: `core/silhouette.py` — flat silhouette render + restore

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/silhouette.py`
- Test: `tests/core/test_silhouette.py`

**Interfaces:**
- Produces `render_silhouette(bpy, obj_name: str | None, preset: str = "ortho4", res: int = 768) -> dict`
  returning `{"available": True, "preset": preset, "images": [{"view","mode":"silhouette","mimeType":"image/png","encoding":"base64","data"}]}`
  or `{"available": False, "reason": str}`. Read-only: original `material_slots` and per-polygon
  `material_index` are restored before returning.

Study `blender_addon/niua_mcp_bridge/core/overlay.py` first — it is the exact template for the
material-snapshot → assign emission → render → restore lifecycle (including the `try/finally`
restore and the `from . import capture as cap` usage). This task is the single-flat-fill analogue.

- [ ] **Step 1: Write the failing test** (mirror the recording-fake-bpy style used by `tests/core/` for overlay/capture; if unsure, read an existing `tests/core/test_*capture*`/overlay test first):

```python
# tests/core/test_silhouette.py
from __future__ import annotations
from niua_mcp_bridge.core import silhouette


def test_render_silhouette_assigns_flat_fill_and_restores(fake_bpy_recording_mesh):
    # fake_bpy_recording_mesh: a fake bpy exposing one mesh object with >=1 material slot,
    # recording render.opengl calls. Reuse/extend the fixture the overlay test uses.
    bpy = fake_bpy_recording_mesh
    obj = bpy.data.objects.get("Cube")
    before_slots = [s.material for s in obj.material_slots]
    before_idx = [p.material_index for p in obj.data.polygons]

    out = silhouette.render_silhouette(bpy, "Cube", preset="ortho4", res=256)

    assert out["available"] is True
    assert out["preset"] == "ortho4"
    assert out["images"] and all(im["mode"] == "silhouette" for im in out["images"])
    # one image per ortho4 view
    assert {im["view"] for im in out["images"]} == {"front", "right", "top", "persp"}
    # materials + indices restored byte-identical
    assert [s.material for s in obj.material_slots] == before_slots
    assert [p.material_index for p in obj.data.polygons] == before_idx


def test_render_silhouette_non_mesh_degrades():
    class _Empty:
        type = "EMPTY"
    class _BpyNoMesh:
        class data:
            class objects:
                @staticmethod
                def get(_n): return _Empty()
    out = silhouette.render_silhouette(_BpyNoMesh, "X")
    assert out["available"] is False and "reason" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_silhouette.py -q`
Expected: FAIL (module `silhouette` not found). If the fake-bpy fixture name differs, first read the
overlay test to copy its exact fixture/import style, then adjust the test above to match before implementing.

- [ ] **Step 3: Implement `render_silhouette`** (mirror `overlay.py`; single flat emission fill):

```python
# blender_addon/niua_mcp_bridge/core/silhouette.py
"""Silhouette eye: render the object as a flat, unlit fill so FORM/proportion read cleanly.

render.opengl(view_context=False) ignores Workbench shading, so (like the topology overlay) we
assign a flat EMISSION material and render through EEVEE, then restore the object exactly.
"""
from __future__ import annotations

from typing import Any

# Bright flat fill: the object reads as a uniform bright shape against the darker EEVEE world,
# so the silhouette outline and proportion are unambiguous regardless of scene lighting.
FILL_RGBA = (0.86, 0.86, 0.88, 1.0)


def _ensure_fill_material(bpy: Any) -> Any:
    name = "__niua_silhouette_fill"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = FILL_RGBA
    emi.inputs["Strength"].default_value = 1.0
    nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = FILL_RGBA
    return mat


def _active_mesh(bpy: Any) -> Any:
    vl = getattr(getattr(bpy, "context", None), "view_layer", None)
    objs = getattr(vl, "objects", None)
    return getattr(objs, "active", None)


def render_silhouette(bpy: Any, obj_name: str | None, preset: str = "ortho4", res: int = 768) -> dict:
    from . import capture as cap

    try:
        obj = bpy.data.objects.get(obj_name) if obj_name else _active_mesh(bpy)
        if obj is None or getattr(obj, "type", None) != "MESH":
            return {"available": False, "reason": f"not a mesh object: {obj_name}"}
        mesh = obj.data
        orig_mats = [slot.material for slot in getattr(obj, "material_slots", [])]
        orig_index = [p.material_index for p in mesh.polygons]
        center, size = cap.scene_bbox(bpy, obj_name)
        cam_obj = cap._ensure_capture_camera(bpy)

        if preset == "orbit4":
            frames = [("orbit_%d" % a, cap.orbit_camera(center, size, a)) for a in (0, 90, 180, 270)]
        else:
            names = cap.PRESETS.get(preset, cap.PRESETS["ortho4"])
            frames = [(n, cap.view_camera(center, size, n)) for n in names]

        images: list[dict] = []
        try:
            obj.data.materials.clear()
            obj.data.materials.append(_ensure_fill_material(bpy))
            for p in mesh.polygons:
                p.material_index = 0
            for name, frame in frames:
                cap._apply_frame(cam_obj, frame)
                data = cap._render_to_b64(bpy, cam_obj, "MATERIAL", res)
                images.append({"view": name, "mode": "silhouette", "mimeType": "image/png", "encoding": "base64", "data": data})
        finally:
            obj.data.materials.clear()
            for m in orig_mats:
                obj.data.materials.append(m)
            for p, idx in zip(mesh.polygons, orig_index):
                p.material_index = idx

        return {"available": True, "preset": preset, "images": images}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/core/test_silhouette.py -q`
Expected: PASS. Adjust the fake-bpy fixture wiring (not the production logic) if the recording
harness needs node-tree/materials stubs — match the overlay test's fixture.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/silhouette.py tests/core/test_silhouette.py
git commit -m "feat: add silhouette form-perception render core"
```

---

## Task 2: Wire `feedback.silhouette` (server spec + addon handler)

**Files:**
- Modify: `src/niua_blender_mcp/domains/feedback.py` (add `ToolSpec` to `SPECS`)
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py` (add handler + register in `COMMANDS`)
- Test: `tests/test_parity.py` (must stay green — no edit expected, just verify)

**Interfaces:**
- Produces tool `feedback.silhouette`, params `object: Str(optional)`, `preset: Enum("ortho4","ortho6","orbit4", default "ortho4")`, `res: Int(default 768, min 64, max 2048)`; `mutates=False`.
- Handler returns `render_silhouette(...)` output, and when available **and** the object is a mesh,
  merges `"proportion": _proportion(obj)` and `"symmetry": _symmetry(mesh)` (reuse the existing
  module functions — do not reimplement). On `available: False`, return it unchanged.

- [ ] **Step 1: Add the server `ToolSpec`** in `src/niua_blender_mcp/domains/feedback.py`, mirroring
  the existing `feedback.capture_views` spec (same import of `Str/Enum/Int`, `mutates=False`,
  `command="feedback.silhouette"`). Summary: "Flat silhouette from preset angles + proportion/symmetry — the form eye."

- [ ] **Step 2: Add the addon handler** in `blender_addon/niua_mcp_bridge/domains/feedback.py`:

```python
def silhouette(ctx: Ctx, payload: dict) -> dict:
    from ..core import silhouette as sil
    obj_name = payload.get("object")
    preset = payload.get("preset", "ortho4")
    res = int(payload.get("res", 768))
    out = sil.render_silhouette(ctx.bpy, obj_name, preset=preset, res=res)
    if out.get("available"):
        obj = ctx.bpy.data.objects.get(obj_name) if obj_name else _active_object(ctx.bpy)
        if obj is not None and getattr(obj, "type", None) == "MESH":
            out["proportion"] = _proportion(obj)
            out["symmetry"] = _symmetry(obj.data)
    return out
```
Match the module's existing conventions for resolving the active object and registering the
command (add `Command(name="feedback.silhouette", handler=silhouette, mutates=False, ...)` to
`COMMANDS` exactly like `feedback.capture_views`). If a `_active_object` helper doesn't exist,
reuse whatever the sibling handlers use to resolve `payload["object"]` → active.

- [ ] **Step 3: Verify registration + parity**

Run:
```bash
python -c "import sys; sys.path.insert(0,'src'); from niua_blender_mcp.domains import build_router as b; print('feedback.silhouette' in {s.name for s in b().specs()})"
pytest tests/test_parity.py tests/domains/test_feedback.py -q
```
Expected: `True`, then PASS (parity holds; server SPEC ↔ addon COMMAND names match).

- [ ] **Step 4: Commit**

```bash
git add src/niua_blender_mcp/domains/feedback.py blender_addon/niua_mcp_bridge/domains/feedback.py
git commit -m "feat: expose feedback.silhouette form eye (images + proportion/symmetry)"
```

---

## Task 3: Headless envelope smoke + full suite

**Files:**
- Modify: `tests/test_smoke_headless.py`

**Interfaces:** Consumes the live bridge like the sibling `feedback.*` smoke tests.

- [ ] **Step 1: Add the envelope test** mirroring `test_feedback_capture_views_returns_envelope`:

```python
def test_feedback_silhouette_returns_envelope(bridge):
    # A cube exists (create if the harness doesn't provide one, per sibling tests).
    out = bridge.call("feedback.silhouette", {"object": "Cube", "preset": "ortho4", "res": 128})
    assert "available" in out
    if out["available"]:
        assert out["images"] and all(im.get("mode") == "silhouette" for im in out["images"])
        assert "proportion" in out and "symmetry" in out
    else:
        assert "reason" in out
```
Match the exact fixture/harness (`bridge`, object setup) the other `feedback.*` smoke tests use in
this file — read one first.

- [ ] **Step 2: Run the targeted smoke + full suite**

Run: `pytest tests/test_smoke_headless.py -q` then `pytest -q`
Expected: PASS (headless returns `available: False` gracefully with no GL; envelope asserted either way).
Full suite green.

- [ ] **Step 3: Commit**

```bash
git add tests/test_smoke_headless.py
git commit -m "test: cover feedback.silhouette graceful-degrade envelope"
```

---

## Acceptance (not a TDD step — done by the controller)

Live visual verification happens when the altimeter is re-run against a visible Blender: the
silhouette renders must show a clean flat form (bright object on dark bg), not gray clay and not
byte-identical across angles. This wave's unit + parity + envelope tests are the mergeable gate;
the perceptual lift shows up in the next altimeter reading.

## Self-Review notes

- Read-only contract enforced by `test_render_silhouette_assigns_flat_fill_and_restores` (materials
  + indices restored).
- No duplicated logic: framing/render reused from `capture.py`, metrics reused from feedback's
  `_proportion`/`_symmetry`, lifecycle mirrors `overlay.py`.
- Interface names consistent: `render_silhouette(bpy, obj_name, preset, res)` used identically in
  Task 1 (impl), Task 2 (handler), and the tests.
