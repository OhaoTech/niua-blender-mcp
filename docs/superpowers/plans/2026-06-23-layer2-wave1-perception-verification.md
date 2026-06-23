# Layer 2 Wave 1 Perception + Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic perception and verification foundation for the senior game-asset pipeline.

**Architecture:** Keep Layer 1 tool parity intact and add Layer 2 eyes/metrics as normal MCP domains. Every new perception tool returns image evidence plus structured analytics. Every metric is deterministic, unit-tested against known meshes, and foldable into `feedback.quality` for later pipeline gates.

**Tech Stack:** Python 3.11+, stdlib only, Blender `bpy` only inside add-on handlers, existing MCP domain/spec pattern, pytest, live smoke tests through the current headless Blender bridge.

## Global Constraints

- No runtime dependencies beyond the existing project dependencies.
- Preserve the server/add-on parity contract: every server `ToolSpec` must have a matching add-on `Command`.
- Read-only eyes use `mutates=False` and must not push undo.
- Temporary visual materials, modifiers, render settings, and object state must be restored in `finally`.
- If rendering is unavailable, visual tools return `{"available": false, "reason": ...}` instead of raising.
- Every build task updates `docs/layer2-architecture.html` so the architecture map stays current.
- Do not build `pipeline.*` state-machine tools in Wave 1; that is Wave 2.

---

## File Map

- `blender_addon/niua_mcp_bridge/core/uv_metrics.py` — pure/bmesh UV analytics: UV bounds, out-of-bounds loops, UV area, mesh area, texel-density estimate, overlap placeholder flag.
- `blender_addon/niua_mcp_bridge/core/orientation_metrics.py` — pure/bmesh orientation analytics: face normal consistency, inward-facing estimate, degenerate face count.
- `blender_addon/niua_mcp_bridge/core/overlay.py` — existing topology overlay plus new reusable material/restore helpers for visual eyes.
- `blender_addon/niua_mcp_bridge/domains/feedback.py` — fold new UV/orientation metrics into `feedback.quality` and `feedback.critique`.
- `blender_addon/niua_mcp_bridge/domains/eyes.py` — add new read-only eyes: `feedback.uv`, `feedback.orientation`, `feedback.wire_shaded`, `feedback.lookdev`.
- `src/niua_blender_mcp/domains/feedback.py` — server spec summary for expanded `feedback.quality`.
- `src/niua_blender_mcp/domains/eyes.py` — server specs for new eyes.
- `tests/core/test_uv_metrics.py` — fake/pure tests for UV metric math.
- `tests/core/test_orientation_metrics.py` — fake/pure tests for orientation metric math.
- `tests/domains/test_eyes.py` — fake render-degrade and command exposure tests.
- `tests/domains/test_quality.py` — expanded fake quality tests.
- `tests/test_smoke_headless.py` — live Blender smoke tests for known cube/n-gon/UV cases.
- `docs/layer2-architecture.html` — visual progress map updated after each task.

---

### Task 1: UV Analytics Block

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/uv_metrics.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/uv.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py`
- Test: `tests/core/test_uv_metrics.py`
- Test: `tests/domains/test_quality.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Consumes: mesh objects with `data.polygons`, `data.vertices`, and optional Blender `bmesh`.
- Produces: `uv_quality(obj: Any, *, texture_size: int = 1024) -> dict`.
- Returned dict shape:

```python
{
    "has_uvs": bool,
    "uv_layer_count": int,
    "active_uv_layer": str | None,
    "island_count": int | None,
    "uv_bounds": {"min_u": float | None, "min_v": float | None, "max_u": float | None, "max_v": float | None},
    "out_of_bounds_loops": int | None,
    "uv_area": float | None,
    "mesh_area": float | None,
    "texel_density_px_per_unit": float | None,
    "overlap_detected": bool | None,
    "stretch_ratio": float | None,
}
```

- [ ] **Step 1: Write failing UV metric tests**

Create `tests/core/test_uv_metrics.py` with tests for:

```python
from niua_mcp_bridge.core.uv_metrics import polygon_area_2d, uv_bounds_from_points


def test_polygon_area_2d_unit_square():
    assert polygon_area_2d([(0, 0), (1, 0), (1, 1), (0, 1)]) == 1.0


def test_polygon_area_2d_triangle():
    assert polygon_area_2d([(0, 0), (1, 0), (0, 1)]) == 0.5


def test_uv_bounds_from_points_counts_out_of_bounds():
    out = uv_bounds_from_points([(0.0, 0.0), (1.0, 1.0), (1.2, -0.1)])
    assert out == {
        "min_u": 0.0,
        "min_v": -0.1,
        "max_u": 1.2,
        "max_v": 1.0,
        "out_of_bounds_loops": 1,
    }
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/core/test_uv_metrics.py -v`

Expected: import failure for `niua_mcp_bridge.core.uv_metrics`.

- [ ] **Step 3: Implement pure helpers**

Create `blender_addon/niua_mcp_bridge/core/uv_metrics.py`:

```python
"""UV quality metrics for Layer 2 gates.

Pure helpers are unit-testable outside Blender. ``uv_quality`` uses bmesh when
available and degrades individual fields to None when fake-bpy lacks UV loop data.
"""

from __future__ import annotations

import math
from typing import Any


def polygon_area_2d(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    acc = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


def uv_bounds_from_points(points: list[tuple[float, float]]) -> dict:
    if not points:
        return {"min_u": None, "min_v": None, "max_u": None, "max_v": None, "out_of_bounds_loops": 0}
    us = [p[0] for p in points]
    vs = [p[1] for p in points]
    out = sum(1 for u, v in points if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0)
    return {"min_u": min(us), "min_v": min(vs), "max_u": max(us), "max_v": max(vs), "out_of_bounds_loops": out}


def uv_quality(obj: Any, *, texture_size: int = 1024) -> dict:
    from niua_mcp_bridge.domains.uv import report as uv_report  # imported lazily to avoid domain import cycles

    # ``uv_report`` needs a Ctx, so this function fills only fields available from object data
    # and bmesh; the domain layer merges layer/island counts from uv.report.
    return _bmesh_uv_quality(obj, texture_size=texture_size)


def _bmesh_uv_quality(obj: Any, *, texture_size: int) -> dict:
    layers = list(getattr(getattr(obj, "data", None), "uv_layers", []) or [])
    active = getattr(getattr(getattr(obj, "data", None), "uv_layers", None), "active", None)
    base = {
        "has_uvs": len(layers) > 0,
        "uv_layer_count": len(layers),
        "active_uv_layer": getattr(active, "name", None) if active is not None else None,
        "uv_bounds": {"min_u": None, "min_v": None, "max_u": None, "max_v": None},
        "out_of_bounds_loops": None,
        "uv_area": None,
        "mesh_area": None,
        "texel_density_px_per_unit": None,
        "overlap_detected": None,
        "stretch_ratio": None,
    }
    try:
        import bmesh  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return base

    mesh = obj.data
    if not layers:
        base["out_of_bounds_loops"] = 0
        return base

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            base["out_of_bounds_loops"] = 0
            return base
        uv_points: list[tuple[float, float]] = []
        uv_area = 0.0
        mesh_area = 0.0
        ratios: list[float] = []
        for face in bm.faces:
            face_uvs = [(float(loop[uv_layer].uv[0]), float(loop[uv_layer].uv[1])) for loop in face.loops]
            uv_points.extend(face_uvs)
            face_uv_area = polygon_area_2d(face_uvs)
            face_mesh_area = float(face.calc_area())
            uv_area += face_uv_area
            mesh_area += face_mesh_area
            if face_uv_area > 0 and face_mesh_area > 0:
                ratios.append(math.sqrt(face_mesh_area) / math.sqrt(face_uv_area))
        bounds = uv_bounds_from_points(uv_points)
        base["uv_bounds"] = {k: bounds[k] for k in ("min_u", "min_v", "max_u", "max_v")}
        base["out_of_bounds_loops"] = bounds["out_of_bounds_loops"]
        base["uv_area"] = uv_area
        base["mesh_area"] = mesh_area
        if uv_area > 0 and mesh_area > 0:
            base["texel_density_px_per_unit"] = texture_size * math.sqrt(uv_area / mesh_area)
        if ratios:
            base["stretch_ratio"] = max(ratios) / min(ratios) if min(ratios) > 0 else None
        base["overlap_detected"] = None
        return base
    finally:
        bm.free()
```

- [ ] **Step 4: Fold into `uv.report` and `feedback.quality`**

Extend `uv.report` to include the new fields, and extend `feedback.quality` with a top-level `"uv"` block. Preserve existing keys.

- [ ] **Step 5: Add quality test**

In `tests/domains/test_quality.py`, assert fake-bpy degradation:

```python
def test_quality_includes_uv_block_with_fake_bpy_degrade(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS, uv_layers=1)))
    out = _quality(env, "Cube")
    assert out["uv"]["has_uvs"] is True
    assert out["uv"]["uv_layer_count"] == 1
    assert out["uv"]["texel_density_px_per_unit"] is None
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/core/test_uv_metrics.py tests/domains/test_quality.py tests/test_parity.py -v`

- [ ] **Step 7: Update architecture HTML**

In `docs/layer2-architecture.html`, mark “UV gates” as next/partly built and add `uv metrics` under current Layer 2 seed.

- [ ] **Step 8: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/uv_metrics.py blender_addon/niua_mcp_bridge/domains/uv.py blender_addon/niua_mcp_bridge/domains/feedback.py tests/core/test_uv_metrics.py tests/domains/test_quality.py docs/layer2-architecture.html
git commit -m "feat: add Layer 2 UV quality metrics"
```

---

### Task 2: Orientation / Normals Analytics Block

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/orientation_metrics.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py`
- Test: `tests/core/test_orientation_metrics.py`
- Test: `tests/domains/test_quality.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces: `orientation_quality(obj: Any) -> dict`.
- Returned dict shape:

```python
{
    "degenerate_faces": int | None,
    "inward_facing_faces": int | None,
    "inward_facing_ratio": float | None,
    "normal_consistency": float | None,
}
```

- [ ] **Step 1: Write failing pure tests**

Create `tests/core/test_orientation_metrics.py`:

```python
from niua_mcp_bridge.core.orientation_metrics import normal_consistency


def test_normal_consistency_all_aligned():
    assert normal_consistency([(0, 0, 1), (0, 0, 1)]) == 1.0


def test_normal_consistency_half_opposed():
    assert normal_consistency([(0, 0, 1), (0, 0, -1)]) == 0.0


def test_normal_consistency_empty_is_none():
    assert normal_consistency([]) is None
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/core/test_orientation_metrics.py -v`

- [ ] **Step 3: Implement orientation helpers**

Create `orientation_metrics.py` with:

```python
"""Normal/orientation metrics for Layer 2 gates."""

from __future__ import annotations

import math
from typing import Any


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float] | None:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length <= 1e-12:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def normal_consistency(normals: list[tuple[float, float, float]]) -> float | None:
    units = [u for n in normals if (u := _unit(n)) is not None]
    if not units:
        return None
    ref = units[0]
    aligned = sum(1 for n in units if (n[0] * ref[0] + n[1] * ref[1] + n[2] * ref[2]) >= 0.0)
    opposed = len(units) - aligned
    return abs(aligned - opposed) / len(units)


def orientation_quality(obj: Any) -> dict:
    base = {
        "degenerate_faces": None,
        "inward_facing_faces": None,
        "inward_facing_ratio": None,
        "normal_consistency": None,
    }
    try:
        import bmesh  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return base

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        normals = [(float(f.normal.x), float(f.normal.y), float(f.normal.z)) for f in bm.faces]
        degenerate = sum(1 for f in bm.faces if f.calc_area() <= 1e-12)
        center = sum((v.co for v in bm.verts), bm.verts[0].co.copy()) / len(bm.verts) if bm.verts else None
        inward = 0
        if center is not None:
            for f in bm.faces:
                direction = f.calc_center_median() - center
                if f.normal.dot(direction) < 0:
                    inward += 1
        face_count = len(bm.faces)
        return {
            "degenerate_faces": degenerate,
            "inward_facing_faces": inward,
            "inward_facing_ratio": (inward / face_count) if face_count else None,
            "normal_consistency": normal_consistency(normals),
        }
    finally:
        bm.free()
```

- [ ] **Step 4: Fold into quality**

Add top-level `"orientation": orientation_quality(obj)` to `feedback.quality`.

- [ ] **Step 5: Test fake-bpy degradation**

Add to `tests/domains/test_quality.py`:

```python
def test_quality_includes_orientation_block_with_fake_bpy_degrade(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    out = _quality(env, "Cube")
    assert out["orientation"] == {
        "degenerate_faces": None,
        "inward_facing_faces": None,
        "inward_facing_ratio": None,
        "normal_consistency": None,
    }
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/core/test_orientation_metrics.py tests/domains/test_quality.py tests/test_parity.py -v`

- [ ] **Step 7: Update architecture HTML**

Mark normals/orientation analytics as built in the perception pillar.

- [ ] **Step 8: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/orientation_metrics.py blender_addon/niua_mcp_bridge/domains/feedback.py tests/core/test_orientation_metrics.py tests/domains/test_quality.py docs/layer2-architecture.html
git commit -m "feat: add Layer 2 orientation quality metrics"
```

---

### Task 3: UV Checker Eye

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/eyes.py`
- Modify: `src/niua_blender_mcp/domains/eyes.py`
- Test: `tests/domains/test_eyes.py`
- Live test: `tests/test_smoke_headless.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces MCP tool: `feedback.uv`.
- Params: `object?: str`, `view?: front|back|left|right|top|bottom|persp`, `res?: int`, `texture_size?: int`.
- Returns:

```python
{
    "available": bool,
    "view": str,
    "analytics": <uv_quality block>,
    "images": [{"view": str, "mode": "checker", "mimeType": "image/png", "data": str}],
}
```

- [ ] **Step 1: Add failing parity/exposure test**

In `tests/domains/test_eyes.py`:

```python
def test_feedback_uv_is_registered():
    from niua_blender_mcp.domains import build_router
    from niua_mcp_bridge.domains import build_default_registry

    specs = {s.name for s in build_router().specs()}
    commands = {c.name for c in build_default_registry().commands}
    assert "feedback.uv" in specs
    assert "feedback.uv" in commands
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/domains/test_eyes.py::test_feedback_uv_is_registered -v`

- [ ] **Step 3: Implement add-on handler**

Implement `uv_checker(ctx, payload)` in `eyes.py`. Use `uv_quality(obj)` for analytics. For visuals, temporarily assign a checker material to the object, render with existing capture engine in `MATERIAL` mode, and restore original material slots in `finally`. If material/node setup fails in headless mode, return `available: false` with analytics preserved.

- [ ] **Step 4: Implement server spec**

Add `ToolSpec(name="feedback.uv", category="feedback", summary="Render UV checker eye and return UV analytics", ...)`.

- [ ] **Step 5: Add live smoke**

In `tests/test_smoke_headless.py`, create a cube, call `uv.smart_unwrap`, then:

```python
out = bridge.call("feedback.uv", {"object": "UVEyeCube", "view": "persp", "res": 256})
assert out["analytics"]["has_uvs"] is True
assert out["images"][0]["mode"] == "checker" or out["available"] is False
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/domains/test_eyes.py tests/test_parity.py -v`

Run: `pytest tests/test_smoke_headless.py::test_feedback_uv_checker_eye -v`

- [ ] **Step 7: Update architecture HTML**

Mark “UV checker” as built and move “UV gates” from missing to next/partial.

- [ ] **Step 8: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/eyes.py src/niua_blender_mcp/domains/eyes.py tests/domains/test_eyes.py tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "feat: add UV checker perception eye"
```

---

### Task 4: Orientation / Backface Eye

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/eyes.py`
- Modify: `src/niua_blender_mcp/domains/eyes.py`
- Test: `tests/domains/test_eyes.py`
- Live test: `tests/test_smoke_headless.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces MCP tool: `feedback.orientation`.
- Params: `object?: str`, `view?: front|back|left|right|top|bottom|persp`, `res?: int`.
- Returns:

```python
{
    "available": bool,
    "view": str,
    "analytics": <orientation_quality block>,
    "images": [{"view": str, "mode": "orientation", "mimeType": "image/png", "data": str}],
}
```

- [ ] **Step 1: Add failing exposure test**

Add `feedback.orientation` to the registration test in `tests/domains/test_eyes.py`.

- [ ] **Step 2: Implement handler/spec**

Render a material pass that makes back-facing/normal-problem inspection possible. Use existing capture framing and restore render/material state. Analytics come from `orientation_quality(obj)`.

- [ ] **Step 3: Add live smoke**

Create a cube and assert:

```python
out = bridge.call("feedback.orientation", {"object": "OrientCube", "view": "persp", "res": 256})
assert "analytics" in out
assert "inward_facing_faces" in out["analytics"]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/domains/test_eyes.py tests/test_parity.py -v`

Run: `pytest tests/test_smoke_headless.py::test_feedback_orientation_eye -v`

- [ ] **Step 5: Update architecture HTML**

Mark normals/backface eye as built.

- [ ] **Step 6: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/eyes.py src/niua_blender_mcp/domains/eyes.py tests/domains/test_eyes.py tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "feat: add orientation perception eye"
```

---

### Task 5: Wire-Over-Shaded and Lookdev Eyes

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/eyes.py`
- Modify: `src/niua_blender_mcp/domains/eyes.py`
- Test: `tests/domains/test_eyes.py`
- Live test: `tests/test_smoke_headless.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces MCP tools: `feedback.wire_shaded`, `feedback.lookdev`.
- `feedback.wire_shaded` returns one material-shaded image plus real wire overlay.
- `feedback.lookdev` returns a turntable-style image set in material/rendered shading and a compact quality analytics block.

- [ ] **Step 1: Add failing exposure tests**

Assert `feedback.wire_shaded` and `feedback.lookdev` exist on server and add-on registries.

- [ ] **Step 2: Implement `feedback.wire_shaded`**

Reuse the topology overlay’s proven real `WIREFRAME` modifier pattern, but render the object’s normal material instead of face-type defect colors.

- [ ] **Step 3: Implement `feedback.lookdev`**

Wrap existing `feedback.turntable`/capture views with `MATERIAL` default shading and include compact `feedback.quality` analytics.

- [ ] **Step 4: Add live smoke tests**

Create a cube with a simple material and assert both tools return `available` images or graceful unavailable results plus analytics.

- [ ] **Step 5: Run tests**

Run: `pytest tests/domains/test_eyes.py tests/test_parity.py -v`

Run: `pytest tests/test_smoke_headless.py::test_feedback_wire_shaded_eye tests/test_smoke_headless.py::test_feedback_lookdev_eye -v`

- [ ] **Step 6: Update architecture HTML**

Mark wire-over-shaded and lookdev turntable as built.

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/eyes.py src/niua_blender_mcp/domains/eyes.py tests/domains/test_eyes.py tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "feat: add wire-shaded and lookdev perception eyes"
```

---

### Task 6: Gate Profiles for Wave 1 Metrics

**Files:**
- Create: `src/niua_blender_mcp/evals/stage_gates.py`
- Test: `tests/evals/test_stage_gates.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces:

```python
def stage_gates(stage: str) -> list[dict]:
    ...
```

- Supported stages in Wave 1: `retopo`, `uv`, `orientation`, `export_preflight`.
- Gate lists use existing `check_gates(metrics, gates)`.

- [ ] **Step 1: Write failing tests**

Create `tests/evals/test_stage_gates.py`:

```python
from niua_blender_mcp.evals.gates import check_gates
from niua_blender_mcp.evals.stage_gates import stage_gates


def test_uv_stage_gates_pass_clean_metrics():
    metrics = {
        "uv": {
            "has_uvs": True,
            "out_of_bounds_loops": 0,
            "overlap_detected": False,
            "stretch_ratio": 1.2,
        }
    }
    assert check_gates(metrics, stage_gates("uv"))["gates_pass"] is True


def test_unknown_stage_raises_key_error():
    try:
        stage_gates("nope")
    except KeyError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("expected KeyError")
```

- [ ] **Step 2: Implement stage gates**

Create `stage_gates.py`:

```python
"""Reusable deterministic gate profiles for Layer 2 stages."""

from __future__ import annotations

_GATES = {
    "retopo": [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.95},
        {"path": "topology.ngons", "op": "==", "value": 0},
        {"path": "topology.non_manifold_edges", "op": "==", "value": 0},
    ],
    "uv": [
        {"path": "uv.has_uvs", "op": "==", "value": True},
        {"path": "uv.out_of_bounds_loops", "op": "==", "value": 0},
        {"path": "uv.overlap_detected", "op": "==", "value": False},
        {"path": "uv.stretch_ratio", "op": "<=", "value": 2.0},
    ],
    "orientation": [
        {"path": "orientation.degenerate_faces", "op": "==", "value": 0},
        {"path": "orientation.inward_facing_faces", "op": "==", "value": 0},
    ],
    "export_preflight": [
        {"path": "scale.transform_applied", "op": "==", "value": True},
        {"path": "topology.non_manifold_edges", "op": "==", "value": 0},
    ],
}


def stage_gates(stage: str) -> list[dict]:
    try:
        return [dict(g) for g in _GATES[stage]]
    except KeyError as exc:
        raise KeyError(f"unknown stage gate profile: {stage}") from exc
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/evals/test_stage_gates.py tests/evals/test_gates.py -v`

- [ ] **Step 4: Update architecture HTML**

Add gate profiles under current Layer 2 seed and keep full `pipeline.*` marked missing.

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/evals/stage_gates.py tests/evals/test_stage_gates.py docs/layer2-architecture.html
git commit -m "feat: add Layer 2 stage gate profiles"
```

---

### Task 7: Wave 1 Live Acceptance

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/layer2-architecture.html`

**Interfaces:**
- Produces one live acceptance test proving a cube can be inspected through the Wave 1 foundation:
  `feedback.quality`, `feedback.topology`, `feedback.uv`, `feedback.orientation`, `feedback.wire_shaded`, and gate profiles.

- [ ] **Step 1: Add acceptance smoke**

Add:

```python
def test_layer2_wave1_perception_foundation_acceptance(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "Wave1Cube"})
    bridge.call("uv.smart_unwrap", {"object": "Wave1Cube", "island_margin": 0.02})
    quality = bridge.call("feedback.quality", {"object": "Wave1Cube"})
    assert quality["topology"]["quad_ratio"] == 1.0
    assert quality["uv"]["has_uvs"] is True
    assert "orientation" in quality
    topo = bridge.call("feedback.topology", {"object": "Wave1Cube", "res": 256})
    uv = bridge.call("feedback.uv", {"object": "Wave1Cube", "res": 256})
    orient = bridge.call("feedback.orientation", {"object": "Wave1Cube", "res": 256})
    wire = bridge.call("feedback.wire_shaded", {"object": "Wave1Cube", "res": 256})
    for eye in (topo, uv, orient, wire):
        assert "available" in eye
```

- [ ] **Step 2: Run acceptance**

Run: `pytest tests/test_smoke_headless.py::test_layer2_wave1_perception_foundation_acceptance -v`

- [ ] **Step 3: Run full verification**

Run:

```bash
pytest -q
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on partial
```

- [ ] **Step 4: Update architecture HTML**

Mark Wave 1 as built, keep Wave 2 as the next highlighted wave.

- [ ] **Step 5: Commit**

```bash
git add tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "test: add Layer 2 Wave 1 live acceptance"
```

---

## Final Verification

- [ ] `pytest -q`
- [ ] `pytest tests/test_smoke_headless.py -v`
- [ ] `python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on partial`
- [ ] `python -c "from niua_blender_mcp.domains import build_router; names={s.name for s in build_router().specs()}; print({'feedback.uv','feedback.orientation','feedback.wire_shaded','feedback.lookdev'} <= names)"`
- [ ] Open `docs/layer2-architecture.html` and confirm Wave 1 is visually marked as built and Wave 2 is marked next.

## Self-Review

- Spec coverage: Covers Wave 1 perception tools and deterministic metrics. Does not build `pipeline.*`; that is explicitly Wave 2.
- Placeholder scan: No `TBD`, `TODO`, or unnamed files remain.
- Type consistency: New metrics use top-level `quality["uv"]` and `quality["orientation"]`; gate profiles reference those exact paths.
