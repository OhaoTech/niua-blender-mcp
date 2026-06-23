# Layer 2 Wave 3 Self-Critique and Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first grounded self-critique loop surface: the agent can load stage standards, compare current metrics against gates and reference targets, and get deterministic repair guidance before retrying a pipeline stage.

**Architecture:** Keep Wave 3 narrow and deterministic. Knowledge is a versioned, human-reviewed pack mirrored on the server and add-on side so MCP calls work inside Blender. Self-critique is not an LLM judge; it is a structured explanation of failed gates plus stage-specific repair suggestions that the driving agent can use between `pipeline.gate_check` and the next edit.

**Tech Stack:** Python 3.11+, stdlib only, existing auto-discovered domain pattern, pytest fake-bpy tests, headless Blender smoke test.

## Global Constraints

- Do not implement autonomous recipe proposal in this wave.
- Do not add external RAG/vector dependencies.
- Do not weaken objective gates; self-critique explains failures, it never overrides them.
- Keep all knowledge packs human-readable and version-controlled.
- Every task updates `docs/layer2-architecture.html`.
- Server/add-on parity must remain green.

---

## File Map

- `blender_addon/niua_mcp_bridge/core/knowledge.py` - add-on embedded stage standards and reference targets.
- `blender_addon/niua_mcp_bridge/domains/knowledge.py` - add-on MCP handlers for `knowledge.list/load`.
- `blender_addon/niua_mcp_bridge/domains/pipeline.py` - add `pipeline.self_critique`.
- `src/niua_blender_mcp/domains/knowledge.py` - server specs for `knowledge.list/load`.
- `src/niua_blender_mcp/domains/pipeline.py` - server spec for `pipeline.self_critique`.
- `src/niua_blender_mcp/knowledge/` - server-side readable copy of the same standards for prompts/tests.
- `tests/core/test_knowledge.py` - pure knowledge tests.
- `tests/domains/test_knowledge.py` - fake-bpy command tests.
- `tests/domains/test_pipeline.py` - self-critique command tests.
- `tests/test_smoke_headless.py` - live Wave 3 acceptance.
- `docs/layer2-architecture.html` - visual map updated after each task.

---

### Task 1: Grounded Knowledge Pack

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/knowledge.py`
- Create: `src/niua_blender_mcp/knowledge/__init__.py`
- Test: `tests/core/test_knowledge.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces:
  - `list_packs() -> list[str]`
  - `load_pack(name: str) -> dict`
  - `stage_pack(stage: str) -> dict`
- Stage names: `repair`, `retopo`, `uv`, `export_preflight`.

- [ ] Write failing tests in `tests/core/test_knowledge.py`:

```python
import pytest

from niua_mcp_bridge.core.knowledge import list_packs, load_pack, stage_pack


def test_lists_stage_knowledge_packs():
    assert list_packs() == ["export_preflight", "repair", "retopo", "uv"]


def test_uv_pack_contains_cited_standards_and_targets():
    pack = stage_pack("uv")
    assert pack["stage"] == "uv"
    assert "texel density" in pack["standards"].lower()
    assert pack["targets"]["overlap_detected"] is False
    assert pack["targets"]["stretch_ratio_max"] == 2.0
    assert pack["sources"]


def test_unknown_pack_is_key_error():
    with pytest.raises(KeyError, match="unknown knowledge pack"):
        load_pack("ghost")
```

- [ ] Run the red test:

```bash
pytest tests/core/test_knowledge.py -v
```

Expected: import error for missing `niua_mcp_bridge.core.knowledge`.

- [ ] Implement `blender_addon/niua_mcp_bridge/core/knowledge.py` with embedded dicts:

```python
"""Grounded Layer 2 stage knowledge packs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_PACKS: dict[str, dict[str, Any]] = {
    "repair": {
        "stage": "repair",
        "standards": "Repair stage validates applied transforms, non-degenerate faces, and outward-facing normals before topology work.",
        "targets": {"degenerate_faces": 0, "inward_facing_faces": 0},
        "sources": [{"title": "Blender Manual - Mesh Normals", "locator": "manual/modeling/meshes/editing/mesh/normals"}],
        "recommendations": {
            "orientation.degenerate_faces": "Remove zero-area faces or merge duplicate vertices, then recalculate normals.",
            "orientation.inward_facing_faces": "Run outward normal recalculation and inspect backface orientation.",
        },
    },
    "retopo": {
        "stage": "retopo",
        "standards": "Game prop retopo should favor clean quads, zero n-gons, and manifold surfaces before UV work.",
        "targets": {"quad_ratio_min": 0.95, "ngons": 0, "non_manifold_edges": 0},
        "sources": [{"title": "Blender Manual - Mesh Cleanup", "locator": "manual/modeling/meshes/editing/mesh/cleanup"}],
        "recommendations": {
            "topology.quad_ratio": "Retopologize large triangle/ngon regions into quads before advancing.",
            "topology.ngons": "Split n-gons into quads or triangles with controlled edge flow.",
            "topology.non_manifold_edges": "Close holes, remove duplicate faces, or repair border edges.",
        },
    },
    "uv": {
        "stage": "uv",
        "standards": "UVs must exist, stay in 0..1 unless intentionally tiled, avoid overlaps, and keep stretch within the stage target.",
        "targets": {"has_uvs": True, "overlap_detected": False, "out_of_bounds_loops": 0, "stretch_ratio_max": 2.0},
        "sources": [{"title": "Blender Manual - UV Editing", "locator": "manual/modeling/meshes/uv"}],
        "recommendations": {
            "uv.has_uvs": "Create a UV layer, unwrap all faces, and pack islands.",
            "uv.out_of_bounds_loops": "Pack islands back into the 0..1 tile or document intentional tiling.",
            "uv.overlap_detected": "Separate overlapping islands and repack with margin.",
            "uv.stretch_ratio": "Add seams or use average island scale before repacking.",
        },
    },
    "export_preflight": {
        "stage": "export_preflight",
        "standards": "Before export, transforms must be applied and the mesh must remain manifold for downstream engines.",
        "targets": {"transform_applied": True, "non_manifold_edges": 0},
        "sources": [{"title": "glTF 2.0 Asset Workflow", "locator": "Khronos glTF 2.0 overview"}],
        "recommendations": {
            "scale.transform_applied": "Apply object transforms before export.",
            "topology.non_manifold_edges": "Repair manifold errors before exporting.",
        },
    },
}


def list_packs() -> list[str]:
    return sorted(_PACKS)


def load_pack(name: str) -> dict[str, Any]:
    try:
        return deepcopy(_PACKS[name])
    except KeyError as exc:
        raise KeyError(f"unknown knowledge pack: {name}") from exc


def stage_pack(stage: str) -> dict[str, Any]:
    return load_pack(stage)
```

- [ ] Add `src/niua_blender_mcp/knowledge/__init__.py` that re-exports the same API from a server-side copy. Keep data values identical to the add-on pack.
- [ ] Run:

```bash
pytest tests/core/test_knowledge.py -v
```

- [ ] Update `docs/layer2-architecture.html` to show `knowledge packs` as built and Wave 3 in progress.
- [ ] Commit:

```bash
git add blender_addon/niua_mcp_bridge/core/knowledge.py src/niua_blender_mcp/knowledge/__init__.py tests/core/test_knowledge.py docs/layer2-architecture.html
git commit -m "feat: add grounded stage knowledge packs"
```

---

### Task 2: knowledge.list/load MCP Tools

**Files:**
- Create: `blender_addon/niua_mcp_bridge/domains/knowledge.py`
- Create: `src/niua_blender_mcp/domains/knowledge.py`
- Test: `tests/domains/test_knowledge.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- MCP tools:
  - `knowledge.list()`
  - `knowledge.load(name)`

- [ ] Write failing tests:

```python
from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeBpy:
    pass


def test_knowledge_tools_registered():
    names = {spec.name for spec in build_router().specs()}
    reg = build_default_registry()
    for name in ("knowledge.list", "knowledge.load"):
        assert name in names
        assert reg.get(name) is not None
        assert reg.get(name).mutates is False


def test_knowledge_list_and_load():
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()
    listed = dispatch_on_main(reg, "knowledge.list", {}, ctx)
    assert "uv" in listed["packs"]
    loaded = dispatch_on_main(reg, "knowledge.load", {"name": "uv"}, ctx)
    assert loaded["pack"]["stage"] == "uv"
    assert loaded["pack"]["targets"]["overlap_detected"] is False
```

- [ ] Run:

```bash
pytest tests/domains/test_knowledge.py tests/test_parity.py -v
```

Expected: missing `knowledge.*` tools.

- [ ] Implement add-on handlers:

```python
"""Knowledge domain handlers."""

from __future__ import annotations

from ..context import Ctx
from ..core import knowledge
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError


def list_knowledge(ctx: Ctx, payload: dict) -> dict:
    return {"packs": knowledge.list_packs()}


def load(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "name is required")
    try:
        return {"pack": knowledge.load_pack(name)}
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc


COMMANDS = [
    Command("knowledge.list", list_knowledge, mutates=False),
    Command("knowledge.load", load, mutates=False),
]
```

- [ ] Implement server specs with `ToolSpec` and `Str(required=True)` for `knowledge.load`.
- [ ] Run:

```bash
pytest tests/domains/test_knowledge.py tests/test_parity.py -v
```

- [ ] Update `docs/layer2-architecture.html` to show `knowledge.list/load` as built.
- [ ] Commit:

```bash
git add blender_addon/niua_mcp_bridge/domains/knowledge.py src/niua_blender_mcp/domains/knowledge.py tests/domains/test_knowledge.py docs/layer2-architecture.html
git commit -m "feat: add knowledge loading tools"
```

---

### Task 3: Deterministic Self-Critique Core

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/self_critique.py`
- Test: `tests/core/test_self_critique.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces:
  - `critique_stage(stage: str, gate_result: dict, pack: dict, *, attempt: int = 1, max_attempts: int = 3) -> dict`

- [ ] Write failing tests:

```python
from niua_mcp_bridge.core.knowledge import stage_pack
from niua_mcp_bridge.core.self_critique import critique_stage


def test_self_critique_explains_failed_uv_gate():
    gate = {
        "gates_pass": False,
        "gates": [
            {"path": "uv.has_uvs", "op": "==", "value": True, "actual": False, "pass": False},
            {"path": "uv.overlap_detected", "op": "==", "value": False, "actual": False, "pass": True},
        ],
    }
    out = critique_stage("uv", gate, stage_pack("uv"), attempt=1, max_attempts=3)
    assert out["stage"] == "uv"
    assert out["failed_count"] == 1
    assert out["may_retry"] is True
    assert out["failed_gates"][0]["path"] == "uv.has_uvs"
    assert "unwrap" in out["recommendations"][0].lower()


def test_self_critique_blocks_retry_at_budget():
    gate = {"gates_pass": False, "gates": [{"path": "uv.has_uvs", "pass": False}]}
    out = critique_stage("uv", gate, stage_pack("uv"), attempt=3, max_attempts=3)
    assert out["may_retry"] is False
```

- [ ] Run:

```bash
pytest tests/core/test_self_critique.py -v
```

- [ ] Implement the pure helper:

```python
"""Deterministic stage self-critique."""

from __future__ import annotations

from typing import Any


def critique_stage(stage: str, gate_result: dict[str, Any], pack: dict[str, Any], *, attempt: int = 1, max_attempts: int = 3) -> dict[str, Any]:
    failed = [gate for gate in gate_result.get("gates", []) if not gate.get("pass", False)]
    recs = []
    suggestions = pack.get("recommendations", {})
    for gate in failed:
        path = gate.get("path", "")
        recs.append(suggestions.get(path, f"Fix gate {path} before advancing."))
    return {
        "stage": stage,
        "attempt": int(attempt),
        "max_attempts": int(max_attempts),
        "gates_pass": bool(gate_result.get("gates_pass", False)),
        "failed_count": len(failed),
        "failed_gates": failed,
        "standards": pack.get("standards", ""),
        "targets": pack.get("targets", {}),
        "sources": pack.get("sources", []),
        "recommendations": recs,
        "may_retry": bool(failed) and int(attempt) < int(max_attempts),
    }
```

- [ ] Run:

```bash
pytest tests/core/test_self_critique.py -v
```

- [ ] Update `docs/layer2-architecture.html` to show deterministic self-critique core as built.
- [ ] Commit:

```bash
git add blender_addon/niua_mcp_bridge/core/self_critique.py tests/core/test_self_critique.py docs/layer2-architecture.html
git commit -m "feat: add deterministic stage self-critique"
```

---

### Task 4: pipeline.self_critique Tool

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/pipeline.py`
- Modify: `src/niua_blender_mcp/domains/pipeline.py`
- Test: `tests/domains/test_pipeline.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- MCP tool:
  - `pipeline.self_critique(object, stage?, attempt=1, max_attempts=3)`
- Returns `{object, stage, gate, critique, state}`.

- [ ] Add failing fake-bpy test:

```python
def test_pipeline_self_critique_returns_repair_guidance_for_failed_uv(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})
    out = _dispatch(env, "pipeline.self_critique", {"object": "Cube", "stage": "uv"})
    assert out["stage"] == "uv"
    assert out["gate"]["gates_pass"] is False
    assert out["critique"]["failed_count"] >= 1
    assert any("unwrap" in rec.lower() for rec in out["critique"]["recommendations"])
```

- [ ] Run:

```bash
pytest tests/domains/test_pipeline.py tests/test_parity.py -v
```

Expected: missing `pipeline.self_critique`.

- [ ] Implement handler by reusing existing `gate_check`, `knowledge.stage_pack`, and `critique_stage`.
- [ ] Add server spec with `Int(default=1, minimum=1, maximum=20)` for `attempt` and `Int(default=3, minimum=1, maximum=20)` for `max_attempts`.
- [ ] Run:

```bash
pytest tests/domains/test_pipeline.py tests/test_parity.py -v
```

- [ ] Update `docs/layer2-architecture.html` to show `pipeline.self_critique` as built.
- [ ] Commit:

```bash
git add blender_addon/niua_mcp_bridge/domains/pipeline.py src/niua_blender_mcp/domains/pipeline.py tests/domains/test_pipeline.py docs/layer2-architecture.html
git commit -m "feat: add pipeline self-critique tool"
```

---

### Task 5: Live Wave 3 Acceptance

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/layer2-architecture.html`

**Flow:**
1. Create `CritPipeHero`.
2. Delete any default UV layers.
3. `pipeline.start`.
4. Advance to `uv`.
5. Call `pipeline.self_critique(stage="uv")`; assert it fails UV gates and recommends unwrap/pack.
6. Run `uv.smart_unwrap` and `uv.pack_islands`.
7. Call `pipeline.self_critique(stage="uv")`; assert gates pass and failed count is 0.

- [ ] Add live acceptance test:

```python
def test_layer2_wave3_self_critique_acceptance(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "CritPipeHero"})
    for layer in bridge.call("uv.layers", {"object": "CritPipeHero"})["layers"]:
        bridge.call("uv.layer_delete", {"object": "CritPipeHero", "name": layer})
    bridge.call("pipeline.start", {"object": "CritPipeHero"})
    assert bridge.call("pipeline.advance", {"object": "CritPipeHero"})["to_stage"] == "repair"
    assert bridge.call("pipeline.advance", {"object": "CritPipeHero"})["to_stage"] == "retopo"
    assert bridge.call("pipeline.advance", {"object": "CritPipeHero"})["to_stage"] == "uv"
    before = bridge.call("pipeline.self_critique", {"object": "CritPipeHero", "stage": "uv"})
    assert before["gate"]["gates_pass"] is False
    assert any("unwrap" in rec.lower() for rec in before["critique"]["recommendations"])
    bridge.call("uv.smart_unwrap", {"object": "CritPipeHero", "island_margin": 0.02})
    bridge.call("uv.pack_islands", {"object": "CritPipeHero", "margin": 0.01})
    after = bridge.call("pipeline.self_critique", {"object": "CritPipeHero", "stage": "uv"})
    assert after["gate"]["gates_pass"] is True
    assert after["critique"]["failed_count"] == 0
```

- [ ] Run:

```bash
pytest tests/test_smoke_headless.py::test_layer2_wave3_self_critique_acceptance -v
```

- [ ] Run final verification:

```bash
pytest -q
pytest tests/test_smoke_headless.py -v
python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on partial
python - <<'PY'
from niua_blender_mcp.domains import build_router
needed = {"knowledge.list", "knowledge.load", "pipeline.self_critique"}
names = {spec.name for spec in build_router().specs()}
missing = sorted(needed - names)
print({"missing": missing, "spec_count": len(names)})
raise SystemExit(1 if missing else 0)
PY
```

- [ ] Update `docs/layer2-architecture.html` to mark Wave 3 built and Wave 4 next.
- [ ] Commit:

```bash
git add tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "test: add Layer 2 Wave 3 self-critique acceptance"
```

---

## Final Verification

- [ ] `pytest -q`
- [ ] `pytest tests/test_smoke_headless.py -v`
- [ ] `python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on partial`
- [ ] Router check: `knowledge.list`, `knowledge.load`, and `pipeline.self_critique` all exposed.
- [ ] Open `docs/layer2-architecture.html` and confirm Wave 3 is marked built and Wave 4 is marked next.

## Self-Review

- Spec coverage: This plan implements grounded standards, reference targets, and bounded per-stage self-critique. It intentionally does not implement autonomous recipe proposal or large knowledge ingestion.
- Placeholder scan: No placeholder markers.
- Type consistency: `knowledge.stage_pack`, `self_critique.critique_stage`, and `pipeline.self_critique` signatures are consistent across tasks.
