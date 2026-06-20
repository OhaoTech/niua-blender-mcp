# Layer 2 — Phase A Scaffold (vertical slice) — Implementation Plan

> **For the implementing agent (Codex):** Self-contained. Execute top-to-bottom,
> one task at a time, each ending green + committed. Steps use `- [ ]`. Run the
> "watch it fail" steps — they prove the test is real. Read the linked existing
> files before editing and mirror their style (terse, typed, comment-rich,
> `from __future__ import annotations` at top of every module). This plan builds
> the senior-artist scaffold **proven end-to-end on ONE competency
> (modeling + topology)**. Wave 2 (UV / bake / materials) is a separate plan that
> repeats these exact patterns — do not build it here.

**Goal:** Ship the Layer-2 scaffold as a working vertical slice: a topology
**eye** (overlay render), a deterministic **gate checker**, the modeling **battery
task**, the **harness** that scores an artifact end-to-end, a **judge interface +
stub**, and the **playbook store** + one seed recipe + one seed craft verb — so the
Phase-B convergence loop has a proven, unit-tested base to run on.

**Architecture:** Perception and scoring split cleanly. The **eye** is bpy-bound
(addon, degrades gracefully headless) and reuses the existing `core/capture.py`
framing camera. The **scoring stack** (`evals/`) is pure Python with NO bpy and NO
network — it takes a metrics dict + dependency-injected callables, so it is fully
unit-testable offline. The **judge** is an interface with a deterministic stub now;
the real multimodal panel is a Phase-B agent.

**Tech Stack:** Python 3.11+, stdlib only. pytest + existing fake-bpy fixtures.
Blender 5.1.x for the bpy-bound smoke tests (skip cleanly without it).

## Global Constraints

- **Zero runtime dependencies.** stdlib only. Do not add packages.
- **Python ≥ 3.11**, `from __future__ import annotations` at top of every module.
- **Standalone / decoupled.** No "niua"/Godot/orchestrator references in code.
- **Two-process contract.** Server `SPECS: list[ToolSpec]` in `src/niua_blender_mcp/domains/`; addon `COMMANDS: list[Command]` in `blender_addon/niua_mcp_bridge/domains/`. A parity test (`tests/test_parity.py`) enforces name-for-name match. Both auto-discovered — never edit a domain `__init__.py`.
- **`bpy` only via `ctx.bpy`** in addon handlers; import `mathutils` directly (NOT `bpy.mathutils`) — see `core/capture.py::_Vector`.
- **All feedback/eye tools are read-only** (`mutates=False`) and MUST degrade to `{"available": False, "reason": ...}` on any render failure (headless/no-GPU). Never raise out of a render path.
- **Undo pushed AFTER success** for mutating tools (see `dispatch.py`). The one craft verb here mutates; follow the pattern.
- **Run tests from repo root:** `pytest`. Commit after every task.

---

## File map

**Create:**
- `blender_addon/niua_mcp_bridge/core/overlay.py` — topology face-type grouping (pure) + overlay render (bpy-bound).
- `blender_addon/niua_mcp_bridge/domains/eyes.py` — addon COMMANDS for `feedback.topology` (+ the seed craft verb `model.retopo_quads` lives in `domains/modeling_verbs.py`, see Task 9).
- `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py` — addon COMMANDS for `model.retopo_quads`.
- `src/niua_blender_mcp/domains/eyes.py` — server SPECS for `feedback.topology`.
- `src/niua_blender_mcp/domains/modeling_verbs.py` — server SPECS for `model.retopo_quads`.
- `src/niua_blender_mcp/evals/__init__.py` — package marker.
- `src/niua_blender_mcp/evals/gates.py` — deterministic gate checker.
- `src/niua_blender_mcp/evals/judge.py` — judge interface + deterministic stub.
- `src/niua_blender_mcp/evals/harness.py` — end-to-end task runner → scorecard.
- `src/niua_blender_mcp/evals/battery/__init__.py` — battery loader.
- `src/niua_blender_mcp/evals/battery/modeling_prop/task.json` — the modeling task.
- `src/niua_blender_mcp/evals/battery/modeling_prop/rubric.md` — the modeling rubric.
- `src/niua_blender_mcp/playbooks/__init__.py` — playbook loader.
- `src/niua_blender_mcp/playbooks/modeling.md` — seed retopo/clean-topology recipe.
- Tests: `tests/core/test_overlay.py`, `tests/domains/test_eyes.py`, `tests/domains/test_modeling_verbs.py`, `tests/evals/__init__.py`, `tests/evals/test_gates.py`, `tests/evals/test_judge.py`, `tests/evals/test_harness.py`, `tests/evals/test_battery.py`, `tests/test_playbooks.py`. Additions to `tests/test_smoke_headless.py`.

**Modify:**
- `pyproject.toml` — package-data for battery `*.json`/`*.md` and playbooks `*.md`.

---

## Milestone 1 — The topology eye

### Task 1: Pure face-type grouping

`render.opengl(view_context=False)` renders from the capture camera and **ignores
viewport overlays** (this is why a plain wireframe overlay shows nothing — it's the
root of the known WIREFRAME bug). So the topology eye marks defects with **real
materials** (which DO render), not overlays. Step one is the pure grouping function.

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/overlay.py`
- Test: `tests/core/test_overlay.py`

**Interfaces:**
- Produces: `face_type_groups(polygons) -> dict` where `polygons` is any iterable of objects exposing `.index: int` and a vertex count via `len(p.vertices)`. Returns `{"tris": [idx...], "quads": [idx...], "ngons": [idx...]}` (ngon = >4 sides).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_overlay.py
from niua_mcp_bridge.core.overlay import face_type_groups


class _Poly:
    def __init__(self, index, sides):
        self.index = index
        self.vertices = list(range(sides))


def test_groups_faces_by_side_count():
    polys = [_Poly(0, 3), _Poly(1, 4), _Poly(2, 5), _Poly(3, 4)]
    groups = face_type_groups(polys)
    assert groups == {"tris": [0], "quads": [1, 3], "ngons": [2]}


def test_empty_mesh_groups_empty():
    assert face_type_groups([]) == {"tris": [], "quads": [], "ngons": []}
```

- [ ] **Step 2: Run and watch fail**

Run: `pytest tests/core/test_overlay.py -v`
Expected: FAIL — module `core.overlay` not found.

- [ ] **Step 3: Implement the pure grouping**

```python
# blender_addon/niua_mcp_bridge/core/overlay.py
"""Topology overlay: mark defects with real materials (which render) instead of
viewport overlays (which render.opengl(view_context=False) ignores).

Two layers, like core/capture.py:
* pure grouping (face_type_groups) — unit-testable, no bpy.
* bpy-bound render (topology_overlay) — assigns temp materials by face type,
  renders via the shared capture camera, restores, degrades gracefully.
"""

from __future__ import annotations

from typing import Any, Iterable


def face_type_groups(polygons: Iterable[Any]) -> dict:
    """Group polygon indices by side count: tris (3), quads (4), ngons (>4)."""
    tris: list[int] = []
    quads: list[int] = []
    ngons: list[int] = []
    for p in polygons:
        sides = len(p.vertices)
        if sides == 3:
            tris.append(p.index)
        elif sides == 4:
            quads.append(p.index)
        elif sides > 4:
            ngons.append(p.index)
    return {"tris": tris, "quads": quads, "ngons": ngons}
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/core/test_overlay.py -v`
Expected: PASS (2 passed). (Create `tests/core/__init__.py` if the test dir needs it — check whether `tests/domains/__init__.py` exists; mirror that.)

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/overlay.py tests/core/
git commit -m "feat: pure face-type grouping for topology overlay"
```

---

### Task 2: Topology overlay render + `feedback.topology` tool

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/overlay.py` (add `topology_overlay`)
- Create: `blender_addon/niua_mcp_bridge/domains/eyes.py` (addon COMMANDS)
- Create: `src/niua_blender_mcp/domains/eyes.py` (server SPECS)
- Test: `tests/domains/test_eyes.py`

**Interfaces:**
- Consumes: `core/capture.py` — `scene_bbox`, `view_camera`, `_ensure_capture_camera`, `_apply_frame`, `_render_to_b64` (all already exist). `face_type_groups` (Task 1). `_resolve_mesh` from `domains/mesh.py`.
- Produces:
  - `core/overlay.topology_overlay(bpy, obj_name, view="persp", res=768) -> dict` returning `{"available": True, "view", "groups": {tris,quads,ngons counts}, "images": [{"view","mode":"facetype","data"...}, {"view","mode":"wireframe","data"...}]}` or `{"available": False, "reason": ...}`. It temporarily assigns 3 materials (quad=grey, tri=orange, ngon=red) to the mesh by polygon `material_index`, renders SOLID, then a WIREFRAME render, then **restores original material slots + indices in a finally block** (never leave the user's mesh recolored).
  - Addon `feedback.topology` handler (in `domains/eyes.py`) + server SPEC. `mutates=False`.

- [ ] **Step 1: Write the failing test** (fake-bpy contract test; mirror `tests/domains/test_feedback.py` fixture style — read it first)

```python
# tests/domains/test_eyes.py
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.domains import eyes


class _FakeBpyNoGPU:
    """Minimal fake: object exists, but rendering raises -> graceful degrade."""
    class data:
        class objects:
            @staticmethod
            def get(name):
                return object() if name == "Cube" else None

    # scene_bbox/render path will fail on this fake -> available: False
    class context:
        class scene:
            objects = []


def test_topology_degrades_gracefully_without_gpu():
    ctx = Ctx(_FakeBpyNoGPU())
    out = eyes.topology(ctx, {"object": "Cube"})
    assert out["available"] is False
    assert "reason" in out
    # The reason must be an honest render/bbox failure, NOT a Python bug like a
    # Matrix@tuple TypeError (regression guard from the original mathutils bug).
    assert "Matrix" not in out["reason"]
```

The full visual correctness (defects actually marked) is asserted in the live smoke test (Task 3 / Milestone-end), not here — fake-bpy can't render.

- [ ] **Step 2: Run and watch fail**

Run: `pytest tests/domains/test_eyes.py -v`
Expected: FAIL — `eyes` module not found.

- [ ] **Step 3: Implement `topology_overlay`** (append to `core/overlay.py`)

```python
# --- bpy-bound overlay render (append to core/overlay.py) ---
QUAD_RGBA = (0.30, 0.30, 0.30, 1.0)
TRI_RGBA = (0.95, 0.55, 0.10, 1.0)
NGON_RGBA = (0.90, 0.10, 0.10, 1.0)


def _ensure_marker_materials(bpy: Any) -> list:
    """Create/reuse 3 unlit marker materials [quad, tri, ngon]; return them."""
    names = ["__niua_topo_quad", "__niua_topo_tri", "__niua_topo_ngon"]
    rgbas = [QUAD_RGBA, TRI_RGBA, NGON_RGBA]
    mats = []
    for name, rgba in zip(names, rgbas):
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
        mat.use_nodes = False
        mat.diffuse_color = rgba
        mats.append(mat)
    return mats


def topology_overlay(bpy: Any, obj_name: str | None, view: str = "persp", res: int = 768) -> dict:
    from . import capture as cap  # reuse the framing camera + renderer

    try:
        obj = bpy.data.objects.get(obj_name) if obj_name else bpy.context.view_layer.objects.active
        if obj is None or getattr(obj, "type", None) != "MESH":
            return {"available": False, "reason": f"not a mesh object: {obj_name}"}
        mesh = obj.data
        groups = face_type_groups(mesh.polygons)

        # Snapshot original material slots + per-poly material_index.
        orig_mats = [s.material for s in obj.material_slots]
        orig_index = [p.material_index for p in mesh.polygons]
        center, size = cap.scene_bbox(bpy, obj_name)
        cam_obj = cap._ensure_capture_camera(bpy)
        frame = cap.view_camera(center, size, view)
        cap._apply_frame(cam_obj, frame)

        try:
            # Swap in marker materials: slot 0=quad,1=tri,2=ngon.
            obj.data.materials.clear()
            for mat in _ensure_marker_materials(bpy):
                obj.data.materials.append(mat)
            for p in mesh.polygons:
                sides = len(p.vertices)
                p.material_index = 0 if sides == 4 else (1 if sides == 3 else 2)
            facetype = cap._render_to_b64(bpy, cam_obj, "SOLID", res)
            wire = cap._render_to_b64(bpy, cam_obj, "WIREFRAME", res)
        finally:
            # Restore the user's materials + indices exactly.
            obj.data.materials.clear()
            for mat in orig_mats:
                obj.data.materials.append(mat)
            for p, idx in zip(mesh.polygons, orig_index):
                p.material_index = idx

        return {
            "available": True,
            "view": view,
            "groups": {k: len(v) for k, v in groups.items()},
            "images": [
                {"view": view, "mode": "facetype", "mimeType": "image/png", "encoding": "base64", "data": facetype},
                {"view": view, "mode": "wireframe", "mimeType": "image/png", "encoding": "base64", "data": wire},
            ],
        }
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}
```

- [ ] **Step 4: Implement the addon handler + server spec**

```python
# blender_addon/niua_mcp_bridge/domains/eyes.py
"""Deeper eyes (addon side): topology overlay render. Read-only, degrades headless.

Marks topology defects with real materials (n-gons red, tris orange, quads grey)
because render.opengl(view_context=False) ignores viewport overlays. Restores the
user's materials afterward.
"""

from __future__ import annotations

from ..context import Ctx
from ..dispatch import Command


def topology(ctx: Ctx, payload: dict) -> dict:
    from ..core import overlay
    obj = payload.get("object")
    view = str(payload.get("view", "persp"))
    res = int(payload.get("res", 768))
    return overlay.topology_overlay(ctx.bpy, obj_name=obj, view=view, res=res)


COMMANDS = [
    Command("feedback.topology", topology, mutates=False),
]
```

```python
# src/niua_blender_mcp/domains/eyes.py
"""Deeper eyes (server side): topology overlay. Mirrors domains/eyes.py COMMANDS."""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

_VIEWS = ["front", "back", "left", "right", "top", "bottom", "persp"]

SPECS = [
    ToolSpec(
        name="feedback.topology",
        category="feedback",
        summary="Render a topology overlay: n-gons (red) / tris (orange) / quads (grey) + a wireframe",
        command="feedback.topology",
        params={
            "object": Str(summary="Mesh to inspect (defaults to active)"),
            "view": Enum(_VIEWS, default="persp", summary="Named view to render from"),
            "res": Int(default=768, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/domains/test_eyes.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Parity + full suite**

Run: `pytest`
Expected: green; `tests/test_parity.py` sees `feedback.topology` on both sides.

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/overlay.py blender_addon/niua_mcp_bridge/domains/eyes.py src/niua_blender_mcp/domains/eyes.py tests/domains/test_eyes.py
git commit -m "feat: feedback.topology overlay eye (material-marked defects + wireframe)"
```

---

### Task 3: Live smoke — overlay marks defects + wireframe renders

**Files:**
- Modify: `tests/test_smoke_headless.py` (read its skip-guard + live-bridge fixture first; match its names).

- [ ] **Step 1: Add the checks**

```python
def test_topology_overlay_renders_two_images(live_bridge):  # match the file's fixture name
    # Build a mesh with a deliberate n-gon, then overlay.
    live_bridge.call("scene.create_object", {"type": "CUBE", "name": "TopoT"})
    out = live_bridge.call("feedback.topology", {"object": "TopoT", "view": "persp", "res": 256})
    assert out["available"] is True
    assert len(out["images"]) == 2
    modes = {img["mode"] for img in out["images"]}
    assert modes == {"facetype", "wireframe"}
    # The facetype and wireframe renders must NOT be byte-identical (regression for
    # the render.opengl view_context bug + proof wireframe shading actually differs).
    data = {img["mode"]: img["data"] for img in out["images"]}
    assert data["facetype"] != data["wireframe"]
```

If the file's fixture is not `live_bridge`, use whatever it defines. If the smoke file builds objects differently, follow its existing helper.

- [ ] **Step 2: Run (with Blender + addon serving, else SKIP)**

Run: `pytest tests/test_smoke_headless.py -v`
Expected: PASS if a live bridge is reachable; SKIPPED otherwise.
**If `facetype == wireframe`** the WIREFRAME shading is not applying — fix in `core/capture.py::_configure_engine` (ensure `scene.display.shading.type = "WIREFRAME"` is set on the path `_render_to_b64` uses; verify `scene.display` is the object the workbench render reads). Re-run until they differ.

- [ ] **Step 3: Commit**

```bash
git add tests/test_smoke_headless.py
git commit -m "test: live smoke for topology overlay + wireframe distinctness"
```

---

## Milestone 2 — The deterministic gate checker

### Task 4: `evals/gates.py`

**Files:**
- Create: `src/niua_blender_mcp/evals/__init__.py` (empty), `src/niua_blender_mcp/evals/gates.py`
- Test: `tests/evals/__init__.py` (empty), `tests/evals/test_gates.py`

**Interfaces:**
- Produces: `check_gates(metrics: dict, gates: list[dict]) -> dict`. Each gate = `{"path": "topology.quad_ratio", "op": ">=", "value": 0.95}`; `op ∈ {">=","<=","==","<",">"}`. `metrics` is the nested dict returned by `feedback.quality`. Returns `{"gates": [{"path","op","value","actual","pass"}...], "gates_pass": bool}`. A missing path → that gate `pass=False`, `actual=None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_gates.py
from niua_blender_mcp.evals.gates import check_gates

METRICS = {"topology": {"quad_ratio": 1.0, "ngons": 0, "non_manifold_edges": 0, "pole_count": 8}}


def test_all_gates_pass():
    gates = [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.95},
        {"path": "topology.ngons", "op": "==", "value": 0},
    ]
    out = check_gates(METRICS, gates)
    assert out["gates_pass"] is True
    assert all(g["pass"] for g in out["gates"])


def test_failing_gate_blocks():
    gates = [{"path": "topology.pole_count", "op": "<=", "value": 4}]
    out = check_gates(METRICS, gates)
    assert out["gates_pass"] is False
    assert out["gates"][0]["actual"] == 8


def test_missing_path_fails_safe():
    out = check_gates(METRICS, [{"path": "uv.texel_density", "op": ">=", "value": 100}])
    assert out["gates_pass"] is False
    assert out["gates"][0]["actual"] is None
```

- [ ] **Step 2: Run and watch fail**

Run: `pytest tests/evals/test_gates.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# src/niua_blender_mcp/evals/gates.py
"""Deterministic objective-gate checker — the un-gameable half of the quality signal.

Evaluates hard thresholds against the nested metrics dict from feedback.quality.
Pure Python, no bpy, no network: fully unit-testable offline.
"""

from __future__ import annotations

import operator
from typing import Any

_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "<": operator.lt, ">": operator.gt}


def _dig(metrics: dict, path: str) -> Any:
    cur: Any = metrics
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def check_gates(metrics: dict, gates: list[dict]) -> dict:
    results = []
    all_pass = True
    for g in gates:
        actual = _dig(metrics, g["path"])
        fn = _OPS.get(g["op"])
        ok = bool(actual is not None and fn is not None and fn(actual, g["value"]))
        all_pass = all_pass and ok
        results.append({"path": g["path"], "op": g["op"], "value": g["value"], "actual": actual, "pass": ok})
    return {"gates": results, "gates_pass": all_pass}
```

- [ ] **Step 4: Run + commit**

Run: `pytest tests/evals/test_gates.py -v` → PASS.

```bash
git add src/niua_blender_mcp/evals/__init__.py src/niua_blender_mcp/evals/gates.py tests/evals/
git commit -m "feat: deterministic objective-gate checker"
```

---

## Milestone 3 — Battery, judge, harness

### Task 5: The modeling battery task (data)

**Files:**
- Create: `src/niua_blender_mcp/evals/battery/__init__.py`, `src/niua_blender_mcp/evals/battery/modeling_prop/task.json`, `.../rubric.md`
- Test: `tests/evals/test_battery.py`

**Interfaces:**
- Produces: `load_task(task_id: str) -> dict` reading `battery/<id>/task.json` and inlining `rubric` from `rubric.md`. Returns `{"id","competency","goal","gates":[...],"judge_threshold","rubric"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_battery.py
from niua_blender_mcp.evals.battery import load_task


def test_loads_modeling_task():
    t = load_task("modeling_prop")
    assert t["id"] == "modeling_prop"
    assert t["competency"] == "modeling"
    assert t["gates"]  # non-empty
    assert "rubric" in t and t["rubric"].strip()
    assert isinstance(t["judge_threshold"], (int, float))
```

- [ ] **Step 2: Run and watch fail** → module/data missing.

- [ ] **Step 3: Create the data + loader**

`src/niua_blender_mcp/evals/battery/modeling_prop/task.json`:

```json
{
  "id": "modeling_prop",
  "competency": "modeling",
  "goal": "Produce a game-ready hard-surface prop with clean, all-quad topology: no n-gons, no non-manifold geometry, minimal poles, within the triangle budget, watertight and correctly scaled.",
  "gates": [
    {"path": "topology.quad_ratio", "op": ">=", "value": 0.95},
    {"path": "topology.ngons", "op": "==", "value": 0},
    {"path": "topology.non_manifold_edges", "op": "==", "value": 0},
    {"path": "topology.tris", "op": "<=", "value": 4000}
  ],
  "judge_threshold": 7.0
}
```

`src/niua_blender_mcp/evals/battery/modeling_prop/rubric.md`:

```markdown
# Senior rubric — game-ready hard-surface prop

Score 0–10 on how a senior game artist would judge this prop from the supplied
multi-angle renders + topology overlay. Be skeptical; default low when unsure.

- **Topology flow (0–3):** Edge loops follow form; quads are evenly distributed;
  poles are placed where they relax (not on flat spans or silhouette edges); no
  triangles/n-gons on deforming or highlight areas.
- **Silhouette & proportion (0–3):** Reads cleanly from all angles; proportions
  are believable; no lumps, pinching, or asymmetry that should be symmetric.
- **Game-readiness (0–2):** Triangle count is appropriate for a prop; watertight;
  scale/orientation sane (Z-up, real-world-ish size).
- **Shading (0–2):** No visible shading errors, flipped normals, or faceting that
  smooth shading + correct normals would fix.

Return JSON: {"score": <0-10 float>, "critique": "<2-4 sentences, concrete>"}.
```

`src/niua_blender_mcp/evals/battery/__init__.py`:

```python
"""Senior task battery loader. Each task = a folder with task.json + rubric.md."""

from __future__ import annotations

import json
import os

_HERE = os.path.dirname(__file__)


def load_task(task_id: str) -> dict:
    folder = os.path.join(_HERE, task_id)
    with open(os.path.join(folder, "task.json")) as fh:
        task = json.load(fh)
    with open(os.path.join(folder, "rubric.md")) as fh:
        task["rubric"] = fh.read()
    return task
```

- [ ] **Step 4: Run + commit**

Run: `pytest tests/evals/test_battery.py -v` → PASS.

```bash
git add src/niua_blender_mcp/evals/battery/ tests/evals/test_battery.py
git commit -m "feat: modeling battery task (gates + senior rubric)"
```

---

### Task 6: Judge interface + deterministic stub

**Files:**
- Create: `src/niua_blender_mcp/evals/judge.py`
- Test: `tests/evals/test_judge.py`

**Interfaces:**
- Produces:
  - `Judgement = {"score": float, "critique": str}` (a dict shape; documented).
  - `stub_judge(images: list, overlays: list, rubric: str, *, score: float = 8.0, critique: str = "stub") -> dict` — deterministic; used by harness unit tests and as the default when no real judge is injected.
  - The REAL judge is a Phase-B agent matching the signature `judge(images, overlays, rubric) -> {"score","critique"}`; document this contract in the module docstring. Do NOT implement an LLM call here.

- [ ] **Step 1: Failing test**

```python
# tests/evals/test_judge.py
from niua_blender_mcp.evals.judge import stub_judge


def test_stub_judge_is_deterministic():
    a = stub_judge([], [], "rubric", score=6.5)
    assert a == {"score": 6.5, "critique": "stub"}
```

- [ ] **Step 2: Run/fail → Step 3: Implement**

```python
# src/niua_blender_mcp/evals/judge.py
"""Quality judge contract + deterministic stub.

The REAL judge is a Phase-B multimodal AGENT, run as an adversarial multi-lens
panel: it is given the multi-angle renders, the eye-overlays, and the task rubric,
and returns {"score": float 0-10, "critique": str}. It is NOT implemented here —
deterministic code cannot judge taste. Phase A ships only this contract + a stub so
the harness is unit-testable offline.

Judge signature (Phase B injects a callable with this shape):
    judge(images: list, overlays: list, rubric: str) -> {"score": float, "critique": str}
"""

from __future__ import annotations


def stub_judge(images: list, overlays: list, rubric: str, *, score: float = 8.0, critique: str = "stub") -> dict:
    return {"score": float(score), "critique": critique}
```

- [ ] **Step 4: Run + commit**

```bash
git add src/niua_blender_mcp/evals/judge.py tests/evals/test_judge.py
git commit -m "feat: judge interface + deterministic stub"
```

---

### Task 7: The harness — run a task end-to-end → scorecard

**Files:**
- Create: `src/niua_blender_mcp/evals/harness.py`
- Test: `tests/evals/test_harness.py`

**Interfaces:**
- Consumes: `check_gates` (Task 4), `stub_judge` (Task 6).
- Produces: `run_task(task: dict, *, produce, observe, judge=stub_judge) -> dict`.
  - `produce()` — caller-supplied callable that builds/edits the artifact (Phase B: drives the bridge; tests: a no-op). Returns anything (ignored).
  - `observe() -> {"metrics": dict, "images": list, "overlays": list}` — caller-supplied; Phase B calls `feedback.quality` + `feedback.topology`; tests: returns canned dicts.
  - Flow: `produce()` → `obs = observe()` → `gate = check_gates(obs["metrics"], task["gates"])` → if gates pass, `j = judge(obs["images"], obs["overlays"], task["rubric"])` else `j = {"score": 0.0, "critique": "objective gates failed"}` → `judge_pass = j["score"] >= task["judge_threshold"]` → `passed = gate["gates_pass"] and judge_pass`.
  - Returns scorecard: `{"task": task["id"], "gates": gate["gates"], "gates_pass", "judge_score": j["score"], "judge_critique": j["critique"], "judge_pass", "pass": passed}`.

- [ ] **Step 1: Failing tests**

```python
# tests/evals/test_harness.py
from niua_blender_mcp.evals.harness import run_task

TASK = {
    "id": "modeling_prop",
    "gates": [{"path": "topology.quad_ratio", "op": ">=", "value": 0.95}],
    "judge_threshold": 7.0,
    "rubric": "r",
}


def _obs(quad_ratio):
    return lambda: {"metrics": {"topology": {"quad_ratio": quad_ratio}}, "images": [], "overlays": []}


def test_fails_when_gates_fail():
    card = run_task(TASK, produce=lambda: None, observe=_obs(0.0))
    assert card["gates_pass"] is False
    assert card["pass"] is False
    assert card["judge_score"] == 0.0  # judge not consulted when gates fail


def test_passes_when_gates_and_judge_pass():
    from niua_blender_mcp.evals.judge import stub_judge
    card = run_task(TASK, produce=lambda: None, observe=_obs(1.0),
                    judge=lambda i, o, r: stub_judge(i, o, r, score=9.0))
    assert card["gates_pass"] is True
    assert card["judge_pass"] is True
    assert card["pass"] is True


def test_gates_pass_but_judge_below_threshold():
    card = run_task(TASK, produce=lambda: None, observe=_obs(1.0),
                    judge=lambda i, o, r: {"score": 5.0, "critique": "weak"})
    assert card["gates_pass"] is True
    assert card["pass"] is False
```

- [ ] **Step 2: Run/fail → Step 3: Implement**

```python
# src/niua_blender_mcp/evals/harness.py
"""End-to-end task harness: produce -> observe -> gate -> judge -> scorecard.

Dependency-injected (produce/observe/judge are callables) so it runs offline in
unit tests and against a live bridge in the Phase-B loop. No bpy, no network here.
"""

from __future__ import annotations

from typing import Callable

from .gates import check_gates
from .judge import stub_judge


def run_task(task: dict, *, produce: Callable[[], object], observe: Callable[[], dict],
             judge: Callable[[list, list, str], dict] = stub_judge) -> dict:
    produce()
    obs = observe()
    gate = check_gates(obs.get("metrics", {}), task.get("gates", []))
    if gate["gates_pass"]:
        j = judge(obs.get("images", []), obs.get("overlays", []), task.get("rubric", ""))
    else:
        j = {"score": 0.0, "critique": "objective gates failed"}
    judge_pass = float(j["score"]) >= float(task.get("judge_threshold", 7.0))
    return {
        "task": task.get("id"),
        "gates": gate["gates"],
        "gates_pass": gate["gates_pass"],
        "judge_score": float(j["score"]),
        "judge_critique": j.get("critique", ""),
        "judge_pass": judge_pass,
        "pass": gate["gates_pass"] and judge_pass,
    }
```

- [ ] **Step 4: Run + commit**

```bash
git add src/niua_blender_mcp/evals/harness.py tests/evals/test_harness.py
git commit -m "feat: end-to-end eval harness (produce/observe/gate/judge -> scorecard)"
```

---

## Milestone 4 — Playbook store + seed

### Task 8: Playbook loader + seed recipe

**Files:**
- Create: `src/niua_blender_mcp/playbooks/__init__.py`, `src/niua_blender_mcp/playbooks/modeling.md`
- Test: `tests/test_playbooks.py`

**Interfaces:**
- Produces: `load_playbook(name: str) -> str` (reads `playbooks/<name>.md`; raises `FileNotFoundError` if missing), `list_playbooks() -> list[str]` (stem names of every `.md`).

- [ ] **Step 1: Failing test**

```python
# tests/test_playbooks.py
from niua_blender_mcp.playbooks import list_playbooks, load_playbook


def test_modeling_playbook_loads():
    assert "modeling" in list_playbooks()
    text = load_playbook("modeling")
    assert "topology" in text.lower()
```

- [ ] **Step 2: Run/fail → Step 3: Implement**

```python
# src/niua_blender_mcp/playbooks/__init__.py
"""Playbook store: senior recipes + heuristics the agent reads (the growing Layer 2).

Seeded by hand; extended by the Phase-B convergence loop (each passed battery task
distills what worked into a playbook entry). Plain markdown so it is human-reviewable
in diffs at the checkpoint gate.
"""

from __future__ import annotations

import os

_HERE = os.path.dirname(__file__)


def list_playbooks() -> list[str]:
    return sorted(f[:-3] for f in os.listdir(_HERE) if f.endswith(".md"))


def load_playbook(name: str) -> str:
    with open(os.path.join(_HERE, f"{name}.md")) as fh:
        return fh.read()
```

`src/niua_blender_mcp/playbooks/modeling.md` (seed — concise, real heuristics):

```markdown
# Playbook — clean game-ready topology

Goal: all-quad, even, deformation-friendly topology with a clean silhouette.

## Recipe
1. Block the form first; do not chase detail before proportions read from 4 angles.
2. Keep quads. Convert stray tris/n-gons: select all in Edit Mode, then
   `mesh.tris_convert_to_quads` (or `model.retopo_quads`). Re-check `quad_ratio`.
3. Make normals consistent (`mesh.normals_make_consistent`) and remove doubles
   (`mesh.remove_doubles`) before judging — flipped normals read as shading errors.
4. Place poles where the surface relaxes (corners, flat interiors), never on a
   curved silhouette edge or a flat span you want to stay flat.
5. Apply transforms (scale/rotation) before export; check `transform_applied`.

## Heuristics (what "senior" looks for)
- Even quad density beats raw quad count; long thin quads on curvature pinch shading.
- A pole on the silhouette is almost always wrong — move it inward.
- N-gons are acceptable ONLY on flat, hidden, non-deforming faces — prefer zero.
- If a loop doesn't follow the form, it's decoration; remove it.
```

- [ ] **Step 4: Run + commit**

```bash
git add src/niua_blender_mcp/playbooks/ tests/test_playbooks.py
git commit -m "feat: playbook store + seed modeling/topology recipe"
```

---

## Milestone 5 — Seed craft verb

### Task 9: `model.retopo_quads` (tier-1 composite verb)

A seed craft verb proving the tier-1 pattern: a composite that converts a mesh to
clean quads (tris→quads + consistent normals + remove doubles) in one call. It
mutates, so it follows the undo-after-success contract via the dispatcher.

**Files:**
- Create: `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py` (addon)
- Create: `src/niua_blender_mcp/domains/modeling_verbs.py` (server)
- Test: `tests/domains/test_modeling_verbs.py`

**Interfaces:**
- Consumes: `ctx.ensure` / `ctx.check_poll` (see `context.py`), the same edit-mode + select pattern as `rna_exec.call_operator`.
- Produces: addon handler `retopo_quads(ctx, payload)` running, in Edit Mode with the object active+selected: `mesh.select_all(action="SELECT")`, `mesh.tris_convert_to_quads()`, `mesh.normals_make_consistent()`, `mesh.remove_doubles()`. Returns `{"object": <name>, "applied": ["tris_convert_to_quads","normals_make_consistent","remove_doubles"]}`. Server SPEC `model.retopo_quads`, `mutates=True`, `feedback="viewport"`, `tier="curated"`. Param: `object: Str` (required), `face_threshold: Float` (optional, default 40.0 degrees → passed to tris_convert_to_quads as radians).

- [ ] **Step 1: Failing test** (fake-bpy; mirror `tests/domains/test_mesh.py` / `test_rna_exec.py` fixtures — read them; reuse their fake bpy with an ops recorder)

```python
# tests/domains/test_modeling_verbs.py
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.domains import modeling_verbs as mv
# Reuse the fake bpy used by test_mesh / test_rna_exec (it records bpy.ops calls).
from tests.domains.test_mesh import make_fake_bpy  # if not exported, replicate inline


def test_retopo_quads_runs_the_pipeline():
    bpy = make_fake_bpy_with_object("Cube")  # build a fake with a MESH object "Cube"
    out = mv.retopo_quads(Ctx(bpy), {"object": "Cube"})
    assert out["object"] == "Cube"
    assert out["applied"] == ["tris_convert_to_quads", "normals_make_consistent", "remove_doubles"]
```

If `test_mesh` does not export a reusable builder, copy its fake-bpy setup into this
file (a fake `bpy` whose `ops.mesh.*` are recorded callables and `data.objects.get`
returns a fake MESH object). Match the existing fakes exactly — do not invent APIs.

- [ ] **Step 2: Run/fail → Step 3: Implement**

```python
# blender_addon/niua_mcp_bridge/domains/modeling_verbs.py
"""Seed craft verbs (addon): composite senior operations. model.retopo_quads.

Tier-1 craft verbs encode a pro sequence behind one call. They mutate, so they flow
through the dispatcher's undo-after-success path. bpy only via ctx.bpy.
"""

from __future__ import annotations

import math

from ..context import Ctx
from ..dispatch import Command


def retopo_quads(ctx: Ctx, payload: dict) -> dict:
    obj = payload.get("object")
    if not isinstance(obj, str) or not obj:
        from ..errors import INVALID_PARAMS, BridgeError
        raise BridgeError(INVALID_PARAMS, "object is required")
    thresh = math.radians(float(payload.get("face_threshold", 40.0)))
    ops = ctx.bpy.ops
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ops.mesh.select_all(action="SELECT")
        ops.mesh.tris_convert_to_quads(face_threshold=thresh, shape_threshold=thresh)
        ops.mesh.normals_make_consistent()
        ops.mesh.remove_doubles()
    return {"object": obj, "applied": ["tris_convert_to_quads", "normals_make_consistent", "remove_doubles"]}


COMMANDS = [
    Command("model.retopo_quads", retopo_quads, mutates=True, feedback="viewport"),
]
```

```python
# src/niua_blender_mcp/domains/modeling_verbs.py
"""Seed craft verbs (server): model.retopo_quads. Mirrors the addon COMMANDS."""

from __future__ import annotations

from ..kernel import Float, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="model.retopo_quads",
        category="modeling",
        summary="Convert a mesh to clean quads: tris->quads, consistent normals, merge doubles (one senior step)",
        command="model.retopo_quads",
        params={
            "object": Str(required=True, summary="Mesh object to clean up"),
            "face_threshold": Float(default=40.0, minimum=0.0, maximum=180.0,
                                    summary="Max angle (deg) to merge tri pairs into quads"),
        },
        mutates=True,
        feedback="viewport",
        tier="curated",
    ),
]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/domains/test_modeling_verbs.py -v` → PASS.

- [ ] **Step 5: Parity + full suite**

Run: `pytest`
Expected: green; parity sees `model.retopo_quads` on both sides.

- [ ] **Step 6: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/modeling_verbs.py src/niua_blender_mcp/domains/modeling_verbs.py tests/domains/test_modeling_verbs.py
git commit -m "feat: model.retopo_quads seed craft verb"
```

---

## Task 10: Package data + docs

**Files:**
- Modify: `pyproject.toml`, `docs/PLAN.md`

- [ ] **Step 1: Ship battery + playbook data in the package**

In `pyproject.toml` add (or extend the existing `[tool.setuptools.package-data]` from the Layer-1 manifest work):

```toml
[tool.setuptools.package-data]
"niua_blender_mcp.manifest" = ["*.json"]
"niua_blender_mcp.evals.battery.modeling_prop" = ["*.json", "*.md"]
"niua_blender_mcp.playbooks" = ["*.md"]
```

- [ ] **Step 2: Note the milestone in `docs/PLAN.md`** — add "Layer 2 Phase A (vertical slice): topology eye, gate checker, modeling battery+harness+judge stub, playbook store + retopo seed + model.retopo_quads — DONE. Wave 2 (UV/bake/materials) + Phase B loop next."

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml docs/PLAN.md
git commit -m "chore: package eval/playbook data; note Layer 2 Phase A milestone"
```

---

## Final verification

- [ ] `pytest` → all green (Blender-dependent smoke tests skip cleanly without Blender).
- [ ] `python -c "from niua_blender_mcp.evals.harness import run_task; from niua_blender_mcp.evals.battery import load_task; print(run_task(load_task('modeling_prop'), produce=lambda:None, observe=lambda:{'metrics':{'topology':{'quad_ratio':1.0,'ngons':0,'non_manifold_edges':0,'tris':100}},'images':[],'overlays':[]}))"` → prints a scorecard with `'pass': True` (stub judge scores 8.0 ≥ 7.0).
- [ ] `python -c "from niua_blender_mcp.domains import build_router; r=build_router(); print('model.retopo_quads' in {s.name for s in r.specs()}, 'feedback.topology' in {s.name for s in r.specs()})"` → `True True`.
- [ ] With a live Blender: `pytest tests/test_smoke_headless.py -v` shows the topology overlay producing two distinct images.

## What this unlocks (Phase B — do NOT build here)

Once this is green, the Phase-B convergence loop (a `Workflow` script) can run:
per battery task, an agent attempts with Layer-1 tools + `load_playbook("modeling")`,
`observe()` calls `feedback.quality` + `feedback.topology`, `run_task` scores it with
the **real** multimodal adversarial judge panel (injected as the `judge` callable),
and on pass it distills a new playbook entry + commits at the checkpoint. Wave 2
replicates Tasks 1–9 for UV / bake / materials (their eyes, metrics blocks in
`feedback.quality`, battery tasks, and seed verbs `uv.smart_unwrap_and_pack` /
`bake.normals_high_to_low` / `shading.author_pbr`).
