# Layer 2 Wave 8 Asset-Class Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Wave 8 asset-class profiles so the existing Layer 2 pipeline can run hard-surface, organic, generated-cleanup, and from-scratch prop targets through one deterministic gated spine.

**Architecture:** Add mirrored asset-class registries in the server package and Blender add-on, guarded by parity tests. The add-on registry resolves the selected class, applies defaults only for omitted parameters, applies class-specific gate overrides, and returns asset-class metadata in quality/gate/knowledge outputs.

**Tech Stack:** Python 3, pytest, existing niua MCP `ToolSpec` manifests, add-on `Command` registry, fake-bpy unit tests, HTML architecture doc.

## Global Constraints

- Use mirrored registries, not a single imported file, because server and add-on run in different Python contexts.
- Profile ids are exactly `hard_surface_prop`, `organic_prop`, `generated_cleanup`, and `from_scratch_prop`.
- Store `asset_class` and `profile_version` in pipeline state.
- Missing `asset_class` defaults to `hard_surface_prop`, and the output must show `asset_class_defaulted: true`.
- Explicit numeric parameters override asset-class defaults.
- Class-overridable server params must not inject numeric defaults before the bridge sees the payload.
- Unknown asset class returns `invalid_params` on bridge commands.
- Gate overrides replace only existing base gate paths; invalid override paths fail tests.
- Every quality/gate result returns `asset_class.profile_version`, `effective_defaults`, and `applied_gate_overrides`.
- No full asset generation, sculpt automation, separate organic pipeline, ML/RL tuning, or engine-specific naming in Wave 8.

---

## File Map

- Create `blender_addon/niua_mcp_bridge/core/asset_classes.py`: add-on source of truth for profile data, default resolution, gate override application, and output metadata.
- Create `src/niua_blender_mcp/asset_classes.py`: mirrored server profile data for enum choices and parity tests.
- Create `blender_addon/niua_mcp_bridge/domains/asset_class.py`: add-on handlers for `asset_class.list` and `asset_class.describe`.
- Create `src/niua_blender_mcp/domains/asset_class.py`: server `ToolSpec`s for `asset_class.list` and `asset_class.describe`.
- Modify `blender_addon/niua_mcp_bridge/core/pipeline.py`: persist asset class, return state metadata, and apply gate overrides.
- Modify `blender_addon/niua_mcp_bridge/domains/pipeline.py`: resolve asset class in `pipeline.start`, `pipeline.gate_check`, and `pipeline.self_critique`.
- Modify `blender_addon/niua_mcp_bridge/domains/feedback.py`: apply asset-class defaults before engine/material quality and return asset-class metadata.
- Modify `blender_addon/niua_mcp_bridge/core/knowledge.py`: merge class-specific guidance into stage packs.
- Modify `blender_addon/niua_mcp_bridge/domains/knowledge.py`: accept optional `asset_class`.
- Modify `src/niua_blender_mcp/domains/feedback.py`: add `asset_class`; remove defaults from class-overridable numeric params.
- Modify `src/niua_blender_mcp/domains/pipeline.py`: add `asset_class`; remove defaults from class-overridable numeric params.
- Modify `src/niua_blender_mcp/domains/knowledge.py`: add optional `asset_class`.
- Modify `src/niua_blender_mcp/evals/stage_gates.py`: expose server-side gate override behavior for deterministic eval tests.
- Modify `docs/layer2-architecture.html`: mark Wave 8 built and move the roadmap to class-specific craft workflows.
- Create or modify tests listed in each task.

---

### Task 1: Mirrored Asset-Class Registries

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/asset_classes.py`
- Create: `src/niua_blender_mcp/asset_classes.py`
- Test: `tests/test_asset_classes.py`

**Interfaces:**
- Produces: `ASSET_CLASS_IDS: list[str]`
- Produces: `DEFAULT_ASSET_CLASS: str`
- Produces: `list_asset_classes() -> list[dict[str, Any]]`
- Produces: `get_asset_class(name: str | None) -> dict[str, Any]`
- Produces: `apply_asset_class_defaults(payload: dict[str, Any], state: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]`
- Produces: `apply_gate_overrides(gates: list[dict[str, Any]], profile: dict[str, Any], stage: str) -> tuple[list[dict[str, Any]], dict[str, Any]]`

- [ ] **Step 1: Write the failing registry tests**

Add `tests/test_asset_classes.py`:

```python
from __future__ import annotations

import pytest

from niua_blender_mcp import asset_classes as server_asset_classes
from niua_mcp_bridge.core import asset_classes as addon_asset_classes


def test_server_and_addon_asset_class_registries_match() -> None:
    server = {profile["id"]: profile for profile in server_asset_classes.list_asset_classes()}
    addon = {profile["id"]: profile for profile in addon_asset_classes.list_asset_classes()}

    assert sorted(server) == ["from_scratch_prop", "generated_cleanup", "hard_surface_prop", "organic_prop"]
    assert server == addon


def test_asset_class_defaults_are_returned_as_copies() -> None:
    first = addon_asset_classes.get_asset_class("hard_surface_prop")
    first["defaults"]["triangle_budget"] = 1

    second = addon_asset_classes.get_asset_class("hard_surface_prop")

    assert second["defaults"]["triangle_budget"] == 5000


def test_apply_asset_class_defaults_preserves_explicit_parameters() -> None:
    payload, meta = addon_asset_classes.apply_asset_class_defaults(
        {"asset_class": "organic_prop", "triangle_budget": 1234}
    )

    assert payload["triangle_budget"] == 1234
    assert payload["material_budget"] == 3
    assert meta["id"] == "organic_prop"
    assert meta["profile_version"] == 1
    assert meta["asset_class_defaulted"] is False
    assert meta["effective_defaults"]["triangle_budget"] == 1234


def test_apply_asset_class_defaults_uses_state_when_payload_omits_class() -> None:
    payload, meta = addon_asset_classes.apply_asset_class_defaults(
        {},
        state={"asset_class": "generated_cleanup", "profile_version": 1},
    )

    assert payload["triangle_budget"] == 6000
    assert payload["max_lod_triangle_ratio"] == 0.65
    assert meta["id"] == "generated_cleanup"
    assert meta["asset_class_defaulted"] is False


def test_missing_asset_class_defaults_to_hard_surface_prop() -> None:
    payload, meta = addon_asset_classes.apply_asset_class_defaults({})

    assert payload["triangle_budget"] == 5000
    assert meta["id"] == "hard_surface_prop"
    assert meta["asset_class_defaulted"] is True


def test_unknown_asset_class_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown asset class: nope"):
        addon_asset_classes.get_asset_class("nope")


def test_gate_overrides_replace_existing_paths_only() -> None:
    base = [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.95},
        {"path": "topology.ngons", "op": "==", "value": 0},
    ]
    profile = addon_asset_classes.get_asset_class("generated_cleanup")

    gates, applied = addon_asset_classes.apply_gate_overrides(base, profile, "retopo")

    assert gates == [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.98},
        {"path": "topology.ngons", "op": "==", "value": 0},
    ]
    assert applied == {"retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.98}}}


def test_invalid_gate_override_path_raises_value_error() -> None:
    base = [{"path": "topology.quad_ratio", "op": ">=", "value": 0.95}]
    profile = {
        "id": "bad",
        "profile_version": 1,
        "label": "Bad",
        "summary": "Bad profile",
        "defaults": {},
        "gate_overrides": {"retopo": {"topology.missing": {"op": ">=", "value": 1}}},
        "stage_targets": {},
        "guidance": {},
    }

    with pytest.raises(ValueError, match="invalid gate override path for retopo: topology.missing"):
        addon_asset_classes.apply_gate_overrides(base, profile, "retopo")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_asset_classes.py -q`

Expected: FAIL with `ModuleNotFoundError` or import error for `asset_classes`.

- [ ] **Step 3: Implement the add-on registry**

Create `blender_addon/niua_mcp_bridge/core/asset_classes.py`:

```python
"""Layer 2 asset-class profiles for deterministic game-asset targets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_ASSET_CLASS = "hard_surface_prop"

_PROFILES: dict[str, dict[str, Any]] = {
    "hard_surface_prop": {
        "id": "hard_surface_prop",
        "profile_version": 1,
        "label": "Hard-surface prop",
        "summary": "Structured hard-surface game prop with clean quad topology and tight collision.",
        "defaults": {
            "triangle_budget": 5000,
            "material_budget": 4,
            "texture_budget": 8,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.75,
            "max_lod_bounds_delta": 0.10,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.50,
            "max_texture_size": 2048,
        },
        "gate_overrides": {},
        "stage_targets": {
            "retopo": "Clean mostly-quad hard-surface topology.",
            "uv": "Packed non-overlapping UVs with controlled stretch.",
            "optimize": "Tight collision and at least one reduced LOD.",
        },
        "guidance": {
            "retopo": "Preserve bevel support loops and flat-panel edge flow.",
            "uv": "Keep seams on hard edges and preserve texel consistency across panels.",
            "optimize": "Use split collision hulls for concave silhouettes instead of one loose box.",
        },
    },
    "organic_prop": {
        "id": "organic_prop",
        "profile_version": 1,
        "label": "Organic prop",
        "summary": "Organic or sculpt-derived prop where silhouette preservation is more important than perfect quads.",
        "defaults": {
            "triangle_budget": 8000,
            "material_budget": 3,
            "texture_budget": 8,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.80,
            "max_lod_bounds_delta": 0.18,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.75,
            "max_texture_size": 2048,
        },
        "gate_overrides": {
            "retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.85}},
            "uv": {"uv.stretch_ratio": {"op": "<=", "value": 2.5}},
        },
        "stage_targets": {
            "retopo": "Mostly quads with enough allowance for organic triangle cleanup.",
            "uv": "Lower visible stretch on curved forms, with relaxed numeric tolerance.",
            "optimize": "Preserve broad silhouette while reducing density.",
        },
        "guidance": {
            "retopo": "Keep loops flowing with anatomy or growth direction; avoid poles on silhouettes.",
            "uv": "Place seams on hidden backsides or natural creases.",
            "optimize": "Prefer LODs that preserve the outer silhouette over aggressive triangle cuts.",
        },
    },
    "generated_cleanup": {
        "id": "generated_cleanup",
        "profile_version": 1,
        "label": "Generated cleanup",
        "summary": "Cleanup pass for generated or scanned meshes that need stricter retopo and UV gates.",
        "defaults": {
            "triangle_budget": 6000,
            "material_budget": 4,
            "texture_budget": 8,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.65,
            "max_lod_bounds_delta": 0.12,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.50,
            "max_texture_size": 2048,
        },
        "gate_overrides": {
            "retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.98}},
            "uv": {"uv.stretch_ratio": {"op": "<=", "value": 1.75}},
        },
        "stage_targets": {
            "retopo": "Strict quad cleanup to remove generated topology noise.",
            "uv": "Strict stretch target so projection cleanup does not hide bad geometry.",
            "optimize": "Aggressive LOD reduction after cleanup stabilizes topology.",
        },
        "guidance": {
            "retopo": "Rebuild noisy generated regions instead of preserving accidental triangulation.",
            "uv": "Reunwrap generated islands; do not trust inherited UVs from cleanup inputs.",
            "optimize": "Use stricter LOD reduction after removing duplicate/generated detail.",
        },
    },
    "from_scratch_prop": {
        "id": "from_scratch_prop",
        "profile_version": 1,
        "label": "From-scratch prop",
        "summary": "Freshly authored prop with tighter budgets because topology and materials are controllable from the start.",
        "defaults": {
            "triangle_budget": 4000,
            "material_budget": 3,
            "texture_budget": 6,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.75,
            "max_lod_bounds_delta": 0.10,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.50,
            "max_texture_size": 2048,
        },
        "gate_overrides": {},
        "stage_targets": {
            "retopo": "Author clean quads directly instead of repairing later.",
            "uv": "Plan seams and trim usage while modeling.",
            "optimize": "Stay inside tighter budgets from the first blockout.",
        },
        "guidance": {
            "retopo": "Keep forms simple and purposeful before adding support loops.",
            "uv": "Lay out trims and seams as part of the modeling plan.",
            "optimize": "Do not spend triangles on details that should be baked or textured.",
        },
    },
}

ASSET_CLASS_IDS = sorted(_PROFILES)
_DEFAULT_KEYS = {"asset_class"}


def list_asset_classes() -> list[dict[str, Any]]:
    return [deepcopy(_PROFILES[name]) for name in ASSET_CLASS_IDS]


def get_asset_class(name: str | None) -> dict[str, Any]:
    asset_class = name if isinstance(name, str) and name else DEFAULT_ASSET_CLASS
    try:
        return deepcopy(_PROFILES[asset_class])
    except KeyError as exc:
        raise KeyError(f"unknown asset class: {asset_class}") from exc


def _class_from_payload_or_state(payload: dict[str, Any], state: dict[str, Any] | None) -> tuple[str, bool]:
    raw = payload.get("asset_class")
    if isinstance(raw, str) and raw:
        return raw, False
    if state is not None:
        stored = state.get("asset_class")
        if isinstance(stored, str) and stored:
            return stored, False
    return DEFAULT_ASSET_CLASS, True


def apply_asset_class_defaults(
    payload: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    asset_class, defaulted = _class_from_payload_or_state(payload, state)
    profile = get_asset_class(asset_class)
    merged = dict(payload)
    effective_defaults: dict[str, Any] = {}
    for key, value in profile["defaults"].items():
        if key not in merged or merged[key] is None:
            merged[key] = value
        effective_defaults[key] = merged[key]
    merged["asset_class"] = profile["id"]
    meta = {
        "id": profile["id"],
        "profile_version": profile["profile_version"],
        "label": profile["label"],
        "summary": profile["summary"],
        "asset_class_defaulted": defaulted,
        "effective_defaults": effective_defaults,
        "applied_gate_overrides": {},
    }
    return merged, meta


def apply_gate_overrides(
    gates: list[dict[str, Any]],
    profile: dict[str, Any],
    stage: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = [deepcopy(gate) for gate in gates]
    overrides = deepcopy(profile.get("gate_overrides", {}).get(stage, {}))
    if not overrides:
        return out, {}
    by_path = {gate["path"]: gate for gate in out}
    for path, replacement in overrides.items():
        if path not in by_path:
            raise ValueError(f"invalid gate override path for {stage}: {path}")
        by_path[path].update({"op": replacement["op"], "value": replacement["value"]})
    return out, {stage: overrides}
```

- [ ] **Step 4: Implement the mirrored server registry**

Create `src/niua_blender_mcp/asset_classes.py` with the same public constants and functions as `blender_addon/niua_mcp_bridge/core/asset_classes.py`. Keep `_PROFILES` values byte-for-byte equivalent except imports/module docstring.

- [ ] **Step 5: Run registry tests to verify they pass**

Run: `pytest tests/test_asset_classes.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_asset_classes.py blender_addon/niua_mcp_bridge/core/asset_classes.py src/niua_blender_mcp/asset_classes.py
git commit -m "feat: add Layer 2 asset-class registry"
```

---

### Task 2: Asset-Class List and Describe Tools

**Files:**
- Create: `blender_addon/niua_mcp_bridge/domains/asset_class.py`
- Create: `src/niua_blender_mcp/domains/asset_class.py`
- Test: `tests/domains/test_asset_class.py`

**Interfaces:**
- Consumes: `asset_classes.list_asset_classes()`
- Consumes: `asset_classes.get_asset_class(name)`
- Produces command/spec `asset_class.list`
- Produces command/spec `asset_class.describe`

- [ ] **Step 1: Write the failing domain tests**

Create `tests/domains/test_asset_class.py`:

```python
from __future__ import annotations

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


class FakeBpy:
    pass


def test_asset_class_tools_registered() -> None:
    names = {spec.name for spec in build_router().specs()}
    reg = build_default_registry()

    for name in ("asset_class.list", "asset_class.describe"):
        assert name in names
        command = reg.get(name)
        assert command is not None
        assert command.mutates is False


def test_asset_class_list_returns_summaries() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    out = dispatch_on_main(reg, "asset_class.list", {}, ctx)

    assert [item["id"] for item in out["asset_classes"]] == [
        "from_scratch_prop",
        "generated_cleanup",
        "hard_surface_prop",
        "organic_prop",
    ]
    assert {"id", "label", "summary", "profile_version"} <= set(out["asset_classes"][0])
    assert "defaults" not in out["asset_classes"][0]


def test_asset_class_describe_returns_complete_profile() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    out = dispatch_on_main(reg, "asset_class.describe", {"asset_class": "generated_cleanup"}, ctx)

    profile = out["asset_class"]
    assert profile["id"] == "generated_cleanup"
    assert profile["profile_version"] == 1
    assert profile["defaults"]["triangle_budget"] == 6000
    assert profile["gate_overrides"]["retopo"]["topology.quad_ratio"]["value"] == 0.98
    assert "retopo" in profile["guidance"]


def test_asset_class_describe_unknown_class_fails_cleanly() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "asset_class.describe", {"asset_class": "nope"}, ctx)

    assert exc.value.code == INVALID_PARAMS
    assert "unknown asset class: nope" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domains/test_asset_class.py -q`

Expected: FAIL because the tools are not registered.

- [ ] **Step 3: Implement add-on handlers**

Create `blender_addon/niua_mcp_bridge/domains/asset_class.py`:

```python
"""Asset-class profile command handlers."""

from __future__ import annotations

from ..context import Ctx
from ..core import asset_classes
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError


def list_profiles(ctx: Ctx, payload: dict) -> dict:
    return {
        "asset_classes": [
            {
                "id": profile["id"],
                "label": profile["label"],
                "summary": profile["summary"],
                "profile_version": profile["profile_version"],
            }
            for profile in asset_classes.list_asset_classes()
        ]
    }


def describe(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("asset_class")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "asset_class is required")
    try:
        return {"asset_class": asset_classes.get_asset_class(name)}
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc


COMMANDS = [
    Command("asset_class.list", list_profiles, mutates=False),
    Command("asset_class.describe", describe, mutates=False),
]
```

- [ ] **Step 4: Implement server specs**

Create `src/niua_blender_mcp/domains/asset_class.py`:

```python
"""Asset-class profile tool manifest."""

from __future__ import annotations

from ..asset_classes import ASSET_CLASS_IDS
from ..kernel import Enum, ToolSpec

SPECS = [
    ToolSpec(
        name="asset_class.list",
        category="asset_class",
        summary="List Layer 2 game-asset class profiles",
        command="asset_class.list",
    ),
    ToolSpec(
        name="asset_class.describe",
        category="asset_class",
        summary="Describe one Layer 2 game-asset class profile",
        command="asset_class.describe",
        params={
            "asset_class": Enum(ASSET_CLASS_IDS, required=True, summary="Asset class profile id"),
        },
    ),
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/domains/test_asset_class.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/domains/test_asset_class.py blender_addon/niua_mcp_bridge/domains/asset_class.py src/niua_blender_mcp/domains/asset_class.py
git commit -m "feat: expose asset-class profile tools"
```

---

### Task 3: Persist Asset Class in Pipeline State

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/pipeline.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/pipeline.py`
- Modify: `src/niua_blender_mcp/domains/pipeline.py`
- Test: `tests/domains/test_pipeline.py`

**Interfaces:**
- Consumes: `asset_classes.get_asset_class(name)`
- Produces: `store.start(object_name, profile="game_asset", asset_class="hard_surface_prop", profile_version=1, asset_class_defaulted=False)`

- [ ] **Step 1: Write the failing pipeline state tests**

Add to `tests/domains/test_pipeline.py`:

```python
def test_pipeline_start_persists_explicit_asset_class(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))

    out = _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "generated_cleanup"})

    state = out["state"]
    assert state["asset_class"] == "generated_cleanup"
    assert state["profile_version"] == 1
    assert state["asset_class_defaulted"] is False


def test_pipeline_start_defaults_asset_class_visibly(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))

    out = _dispatch(env, "pipeline.start", {"object": "Cube"})

    state = out["state"]
    assert state["asset_class"] == "hard_surface_prop"
    assert state["profile_version"] == 1
    assert state["asset_class_defaulted"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domains/test_pipeline.py::test_pipeline_start_persists_explicit_asset_class tests/domains/test_pipeline.py::test_pipeline_start_defaults_asset_class_visibly -q`

Expected: FAIL with missing `asset_class` keys.

- [ ] **Step 3: Modify the pipeline state store**

In `blender_addon/niua_mcp_bridge/core/pipeline.py`, change `start` to:

```python
def start(
    object_name: str,
    profile: str = "game_asset",
    asset_class: str = "hard_surface_prop",
    profile_version: int = 1,
    asset_class_defaulted: bool = False,
) -> dict[str, Any]:
    state = {
        "object": object_name,
        "profile": profile,
        "asset_class": asset_class,
        "profile_version": profile_version,
        "asset_class_defaulted": asset_class_defaulted,
        "current_stage": "intake",
        "completed": [],
        "complete": False,
        "gates": {},
        "checkpoints": {"intake": _checkpoint_label("intake")},
    }
    _STORE[object_name] = state
    return status(object_name)
```

- [ ] **Step 4: Resolve asset class in the add-on pipeline handler**

In `blender_addon/niua_mcp_bridge/domains/pipeline.py`, import asset classes:

```python
from ..core import asset_classes
```

Change `start` to:

```python
def start(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    profile = payload.get("profile")
    profile = profile if isinstance(profile, str) and profile else "game_asset"
    raw_asset_class = payload.get("asset_class")
    asset_class_defaulted = not (isinstance(raw_asset_class, str) and raw_asset_class)
    try:
        asset_profile = asset_classes.get_asset_class(raw_asset_class)
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc
    label = "pipeline:intake:entry"
    session_store.checkpoint(obj, label=label)
    return store.start(
        obj.name,
        profile=profile,
        asset_class=asset_profile["id"],
        profile_version=int(asset_profile["profile_version"]),
        asset_class_defaulted=asset_class_defaulted,
    )
```

- [ ] **Step 5: Add server spec parameter**

In `src/niua_blender_mcp/domains/pipeline.py`, import `Enum` and `ASSET_CLASS_IDS`:

```python
from ..asset_classes import ASSET_CLASS_IDS
from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec
```

Add to `pipeline.start` params:

```python
"asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
```

Do not set a server-side default here: the add-on must see an omitted `asset_class` so it can return `asset_class_defaulted: true`.

- [ ] **Step 6: Run pipeline tests**

Run: `pytest tests/domains/test_pipeline.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/pipeline.py blender_addon/niua_mcp_bridge/domains/pipeline.py src/niua_blender_mcp/domains/pipeline.py tests/domains/test_pipeline.py
git commit -m "feat: persist pipeline asset class"
```

---

### Task 4: Apply Asset-Class Defaults in `feedback.quality`

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py`
- Modify: `src/niua_blender_mcp/domains/feedback.py`
- Modify: `src/niua_blender_mcp/domains/pipeline.py`
- Test: `tests/domains/test_quality.py`

**Interfaces:**
- Consumes: `asset_classes.apply_asset_class_defaults(payload, state=None)`
- Produces: `quality()["asset_class"]`

- [ ] **Step 1: Write failing quality tests**

Add to `tests/domains/test_quality.py`:

```python
def test_quality_applies_asset_class_defaults(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS * 1500)
    bpy.add(FakeObj("Cube", data=mesh))

    organic = _quality(env, "Cube", asset_class="organic_prop")["engine"]
    scratch = _quality(env, "Cube", asset_class="from_scratch_prop")["engine"]

    assert organic["triangle_budget"] == 8000
    assert organic["within_triangle_budget"] is True
    assert scratch["triangle_budget"] == 4000
    assert scratch["within_triangle_budget"] is False


def test_quality_reports_asset_class_metadata_and_explicit_overrides(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))

    out = _quality(env, "Cube", asset_class="organic_prop", triangle_budget=1234)

    meta = out["asset_class"]
    assert meta["id"] == "organic_prop"
    assert meta["profile_version"] == 1
    assert meta["asset_class_defaulted"] is False
    assert meta["effective_defaults"]["triangle_budget"] == 1234
    assert meta["effective_defaults"]["material_budget"] == 3
    assert meta["applied_gate_overrides"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domains/test_quality.py::test_quality_applies_asset_class_defaults tests/domains/test_quality.py::test_quality_reports_asset_class_metadata_and_explicit_overrides -q`

Expected: FAIL because quality does not return `asset_class` metadata and does not apply profile defaults.

- [ ] **Step 3: Apply defaults in the add-on quality handler**

In `blender_addon/niua_mcp_bridge/domains/feedback.py`, import asset classes:

```python
from ..core import asset_classes
```

Change `quality` so it creates an effective payload:

```python
def quality(ctx: Ctx, payload: dict) -> dict:
    """Objective quality metrics for a mesh: topology, UVs, orientation, symmetry, proportion, scale, engine/material readiness.

    The numeric judgment channel that complements the multi-angle images — so the agent's
    do->observe->judge->revert loop converges on facts, not vibes. Read-only; bmesh-derived
    fields (pole_count, non_manifold_edges, loose_verts) degrade to ``null`` without bmesh.
    """
    obj = _resolve_mesh(ctx, payload)
    effective_payload, asset_meta = asset_classes.apply_asset_class_defaults(payload)
    mesh = obj.data
    counts = topology_counts(mesh)
    return {
        "object": obj.name,
        "asset_class": asset_meta,
        "topology": _topology_quality(obj, counts),
        "uv": uv_report(ctx, {"object": obj.name}),
        "orientation": orientation_quality(obj),
        "symmetry": _symmetry(mesh),
        "proportion": _proportion(obj),
        "scale": _scale(obj),
        "engine": engine_quality(ctx, obj, counts, effective_payload),
        "material": material_quality(obj, effective_payload),
        "export_profile": export_profile_quality(ctx, obj, counts, effective_payload),
    }
```

Also add `"asset_class": full["asset_class"]` to `_quality_compact`.

- [ ] **Step 4: Remove server defaults for class-overridable params**

In `src/niua_blender_mcp/domains/feedback.py`, import `ASSET_CLASS_IDS` and add the enum:

```python
from ..asset_classes import ASSET_CLASS_IDS
```

Change class-overridable params to omit defaults:

```python
"asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
"triangle_budget": Int(minimum=0, summary="Maximum triangles for the optimize gate"),
"material_budget": Int(minimum=0, summary="Maximum material slots for the optimize gate"),
"texture_budget": Int(minimum=0, summary="Maximum unique image textures for the optimize gate"),
"min_lods": Int(minimum=0, summary="Minimum detected LOD variants for the optimize gate"),
"max_lod_triangle_ratio": Float(minimum=0.0, maximum=1.0, summary="Maximum allowed triangle ratio for each LOD relative to the source"),
"max_lod_bounds_delta": Float(minimum=0.0, maximum=1.0, summary="Maximum relative bounds delta allowed for LOD silhouette preservation"),
"min_collision_hulls": Int(minimum=0, summary="Minimum detected collision hull count"),
"max_collision_oversize_ratio": Float(minimum=0.0, summary="Maximum collision union oversize ratio relative to the source bounds"),
"max_texture_size": Int(minimum=1, summary="Maximum texture dimension for material atlas readiness"),
```

Apply the same no-default rule and `asset_class` enum in `src/niua_blender_mcp/domains/pipeline.py` for `pipeline.gate_check`.

- [ ] **Step 5: Run quality tests**

Run: `pytest tests/domains/test_quality.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/feedback.py src/niua_blender_mcp/domains/feedback.py src/niua_blender_mcp/domains/pipeline.py tests/domains/test_quality.py
git commit -m "feat: apply asset-class quality defaults"
```

---

### Task 5: Apply Asset-Class Gate Overrides in Pipeline Checks

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/pipeline.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/pipeline.py`
- Modify: `src/niua_blender_mcp/evals/stage_gates.py`
- Test: `tests/domains/test_pipeline.py`
- Test: `tests/evals/test_stage_gates.py`

**Interfaces:**
- Consumes: `asset_classes.apply_asset_class_defaults(payload, state)`
- Consumes: `asset_classes.apply_gate_overrides(gates, profile, stage)`
- Produces: class-aware gate list and result metadata.

- [ ] **Step 1: Write failing gate override tests**

Add to `tests/evals/test_stage_gates.py`:

```python
def test_stage_gates_apply_asset_class_overrides():
    organic = stage_gates("retopo", asset_class="organic_prop")
    generated = stage_gates("retopo", asset_class="generated_cleanup")

    assert organic[0] == {"path": "topology.quad_ratio", "op": ">=", "value": 0.85}
    assert generated[0] == {"path": "topology.quad_ratio", "op": ">=", "value": 0.98}
```

Add to `tests/domains/test_pipeline.py`:

```python
def test_gate_check_applies_stored_asset_class_gate_overrides(env):
    _ctx, bpy = env
    polys = _CUBE_QUADS[:5] + [[0, 1, 2]]
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=polys)))
    _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "generated_cleanup"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "retopo"})

    assert out["asset_class"]["id"] == "generated_cleanup"
    assert out["asset_class"]["applied_gate_overrides"]["retopo"]["topology.quad_ratio"]["value"] == 0.98
    assert out["gates"][0]["path"] == "topology.quad_ratio"
    assert out["gates"][0]["value"] == 0.98
    assert out["gates"][0]["actual"] < 0.98


def test_gate_check_accepts_payload_asset_class_override(env):
    _ctx, bpy = env
    polys = _CUBE_QUADS[:5] + [[0, 1, 2]]
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=polys)))
    _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "hard_surface_prop"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "retopo", "asset_class": "organic_prop"})

    assert out["asset_class"]["id"] == "organic_prop"
    assert out["gates"][0]["value"] == 0.85
    assert out["gates"][0]["pass"] is True
```

If bmesh-derived `topology.non_manifold_edges` returns `None` in fake-bpy and prevents the whole gate from passing, assert the first gate path and first gate pass instead of asserting `gates_pass`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/evals/test_stage_gates.py::test_stage_gates_apply_asset_class_overrides tests/domains/test_pipeline.py::test_gate_check_applies_stored_asset_class_gate_overrides tests/domains/test_pipeline.py::test_gate_check_accepts_payload_asset_class_override -q`

Expected: FAIL because `stage_gates` and `pipeline.gate_check` ignore asset classes.

- [ ] **Step 3: Add asset-class support to add-on stage gates**

In `blender_addon/niua_mcp_bridge/core/pipeline.py`, import:

```python
from . import asset_classes
```

Change `stage_gates` to:

```python
def stage_gates(stage: str, asset_class: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile = gate_profile(stage)
    if profile is None:
        return [], {}
    try:
        base = [deepcopy(gate) for gate in _GATES[profile]]
    except KeyError as exc:
        raise ValueError(f"unknown stage gate profile: {profile}") from exc
    asset_profile = asset_classes.get_asset_class(asset_class)
    return asset_classes.apply_gate_overrides(base, asset_profile, stage)
```

Update callers in `gate_check` to unpack `(gates, applied_gate_overrides)`.

- [ ] **Step 4: Resolve asset class in add-on gate check**

In `blender_addon/niua_mcp_bridge/domains/pipeline.py`, change `gate_check`:

```python
def gate_check(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    state = store.get_state(obj.name)
    if state is None:
        raise BridgeError(PRECONDITION, f"pipeline has not started for object: {obj.name}")

    stage = _stage_for_gate_check(obj.name, payload)
    try:
        metrics_payload, asset_meta = asset_classes.apply_asset_class_defaults(payload, state=state)
        gates, applied_gate_overrides = store.stage_gates(stage, asset_class=metrics_payload["asset_class"])
    except (KeyError, ValueError) as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc

    metrics_payload["object"] = obj.name
    metrics = quality(ctx, metrics_payload)
    asset_meta["applied_gate_overrides"] = applied_gate_overrides
    metrics["asset_class"]["applied_gate_overrides"] = applied_gate_overrides
    checked = store.check_gates(metrics, gates)
    gate_record = {
        "stage": stage,
        "gate_profile": store.gate_profile(stage),
        "asset_class": asset_meta,
        **checked,
    }
    state_out = store.record_gate(obj.name, stage, gate_record)
    return {
        "object": obj.name,
        "stage": stage,
        "asset_class": asset_meta,
        "metrics": metrics,
        **checked,
        "state": state_out,
    }
```

Update `advance` if needed to keep `checked["asset_class"]` in recorded gate output.

- [ ] **Step 5: Add server-side eval support**

In `src/niua_blender_mcp/evals/stage_gates.py`, import server asset classes and update `stage_gates`:

```python
from .. import asset_classes


def stage_gates(stage: str, asset_class: str | None = None) -> list[dict[str, Any]]:
    try:
        gates = [deepcopy(gate) for gate in _GATES[stage]]
    except KeyError as exc:
        raise KeyError(stage) from exc
    profile = asset_classes.get_asset_class(asset_class)
    out, _applied = asset_classes.apply_gate_overrides(gates, profile, stage)
    return out
```

Keep `check_gates` unchanged.

- [ ] **Step 6: Run pipeline/eval tests**

Run: `pytest tests/domains/test_pipeline.py tests/evals/test_stage_gates.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/pipeline.py blender_addon/niua_mcp_bridge/domains/pipeline.py src/niua_blender_mcp/evals/stage_gates.py tests/domains/test_pipeline.py tests/evals/test_stage_gates.py
git commit -m "feat: apply asset-class gate overrides"
```

---

### Task 6: Asset-Class Knowledge Guidance and Self-Critique

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/knowledge.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/knowledge.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/pipeline.py`
- Modify: `src/niua_blender_mcp/domains/knowledge.py`
- Test: `tests/domains/test_knowledge.py`
- Test: `tests/domains/test_pipeline.py`

**Interfaces:**
- Consumes: `asset_classes.get_asset_class(name)`
- Produces: `knowledge.load_pack(name, asset_class=None)`
- Produces: `knowledge.stage_pack(stage, asset_class=None)`

- [ ] **Step 1: Write failing knowledge tests**

Add to `tests/domains/test_knowledge.py`:

```python
def test_knowledge_load_accepts_asset_class_guidance():
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    loaded = dispatch_on_main(
        reg,
        "knowledge.load",
        {"name": "retopo", "asset_class": "generated_cleanup"},
        ctx,
    )

    pack = loaded["pack"]
    assert pack["asset_class"]["id"] == "generated_cleanup"
    assert "generated topology noise" in pack["asset_class"]["guidance"]
    assert pack["recommendations"]["topology.quad_ratio"].startswith("Retopologize")


def test_knowledge_load_unknown_asset_class_fails_cleanly():
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "knowledge.load", {"name": "retopo", "asset_class": "nope"}, ctx)

    assert exc.value.code == INVALID_PARAMS
```

If `tests/domains/test_knowledge.py` does not import `pytest`, `BridgeError`, and `INVALID_PARAMS`, add:

```python
import pytest
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError
```

Then keep the `INVALID_PARAMS` assertion above.

Add to `tests/domains/test_pipeline.py`:

```python
def test_pipeline_self_critique_uses_stored_asset_class_guidance(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "generated_cleanup"})

    out = _dispatch(env, "pipeline.self_critique", {"object": "Cube", "stage": "retopo"})

    assert out["critique"]["stage"] == "retopo"
    assert out["gate"]["gates_pass"] is False
    assert out["critique"]["knowledge"]["asset_class"]["id"] == "generated_cleanup"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/domains/test_knowledge.py tests/domains/test_pipeline.py::test_pipeline_self_critique_uses_stored_asset_class_guidance -q`

Expected: FAIL because knowledge packs do not accept asset classes.

- [ ] **Step 3: Add class-aware pack loading**

In `blender_addon/niua_mcp_bridge/core/knowledge.py`, import:

```python
from . import asset_classes
```

Change `load_pack` and `stage_pack`:

```python
def _with_asset_class(pack: dict[str, Any], asset_class: str | None) -> dict[str, Any]:
    if not asset_class:
        return pack
    profile = asset_classes.get_asset_class(asset_class)
    stage = str(pack.get("stage", ""))
    guidance = profile.get("guidance", {}).get(stage)
    pack["asset_class"] = {
        "id": profile["id"],
        "profile_version": profile["profile_version"],
        "label": profile["label"],
        "summary": profile["summary"],
        "guidance": guidance,
    }
    return pack


def load_pack(name: str, asset_class: str | None = None) -> dict[str, Any]:
    try:
        pack = deepcopy(_PACKS[name])
    except KeyError as exc:
        raise KeyError(f"unknown knowledge pack: {name}") from exc
    return _with_asset_class(pack, asset_class)


def stage_pack(stage: str, asset_class: str | None = None) -> dict[str, Any]:
    return load_pack(stage, asset_class=asset_class)
```

- [ ] **Step 4: Thread `asset_class` through handlers**

In `blender_addon/niua_mcp_bridge/domains/knowledge.py`, change `load`:

```python
def load(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "name is required")
    asset_class = payload.get("asset_class")
    try:
        return {"pack": knowledge.load_pack(name, asset_class=asset_class)}
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc
```

In `src/niua_blender_mcp/domains/knowledge.py`, import `ASSET_CLASS_IDS` and `Enum`, then add:

```python
"asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
```

to `knowledge.load` params.

- [ ] **Step 5: Thread stored class into self-critique**

In `blender_addon/niua_mcp_bridge/domains/pipeline.py`, change the pack load in `self_critique`:

```python
state = store.get_state(obj.name)
asset_class = payload.get("asset_class")
if not isinstance(asset_class, str) or not asset_class:
    asset_class = state.get("asset_class") if state else None
pack = knowledge.stage_pack(stage, asset_class=asset_class)
```

Keep the existing `KeyError -> BridgeError(INVALID_PARAMS, ...)` behavior.

- [ ] **Step 6: Run knowledge and pipeline tests**

Run: `pytest tests/domains/test_knowledge.py tests/domains/test_pipeline.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/knowledge.py blender_addon/niua_mcp_bridge/domains/knowledge.py blender_addon/niua_mcp_bridge/domains/pipeline.py src/niua_blender_mcp/domains/knowledge.py tests/domains/test_knowledge.py tests/domains/test_pipeline.py
git commit -m "feat: add asset-class knowledge guidance"
```

---

### Task 7: End-to-End Wave 8 Acceptance and Architecture Diagram

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/layer2-architecture.html`

**Interfaces:**
- Consumes all Wave 8 commands and metadata from Tasks 1-6.
- Produces updated architecture page showing Wave 8 built and next roadmap item.

- [ ] **Step 1: Write failing smoke acceptance**

Add a headless smoke test near the existing Layer 2 pipeline acceptance in `tests/test_smoke_headless.py`:

```python
def test_layer2_wave8_asset_class_profiles_acceptance(bridge: BlenderBridge) -> None:
    bridge.call("object.create", {"type": "CUBE", "name": "ClassHero"})

    classes = bridge.call("asset_class.list", {})
    ids = [item["id"] for item in classes["asset_classes"]]
    assert "generated_cleanup" in ids
    described = bridge.call("asset_class.describe", {"asset_class": "generated_cleanup"})
    assert described["asset_class"]["gate_overrides"]["retopo"]["topology.quad_ratio"]["value"] == 0.98

    started = bridge.call("pipeline.start", {"object": "ClassHero", "asset_class": "organic_prop"})
    assert started["state"]["asset_class"] == "organic_prop"
    assert started["state"]["profile_version"] == 1

    quality = bridge.call("feedback.quality", {"object": "ClassHero", "asset_class": "from_scratch_prop"})
    assert quality["asset_class"]["id"] == "from_scratch_prop"
    assert quality["engine"]["triangle_budget"] == 4000

    organic_retopo = bridge.call(
        "pipeline.gate_check",
        {"object": "ClassHero", "stage": "retopo", "asset_class": "organic_prop"},
    )
    generated_retopo = bridge.call(
        "pipeline.gate_check",
        {"object": "ClassHero", "stage": "retopo", "asset_class": "generated_cleanup"},
    )
    assert organic_retopo["gates"][0]["value"] == 0.85
    assert generated_retopo["gates"][0]["value"] == 0.98

    knowledge = bridge.call("knowledge.load", {"name": "retopo", "asset_class": "generated_cleanup"})
    assert knowledge["pack"]["asset_class"]["id"] == "generated_cleanup"
```

- [ ] **Step 2: Run smoke acceptance to verify it fails**

Run: `pytest tests/test_smoke_headless.py::test_layer2_wave8_asset_class_profiles_acceptance -q`

Expected: FAIL until all prior tasks are integrated in Blender.

- [ ] **Step 3: Update architecture HTML**

In `docs/layer2-architecture.html`:

- Change “Waves 1-7” to “Waves 1-8”.
- Add built chips for `asset_class.list`, `asset_class.describe`, and `asset-class gate overrides`.
- Change the Wave 8 card from `next` to `built`.
- Move the next roadmap item to “Class-specific craft workflows”.
- Update server/add-on counts by running the registry count command in Step 5 and putting the exact values in the first panel.

- [ ] **Step 4: Run focused acceptance and HTML parser**

Run:

```bash
pytest tests/test_smoke_headless.py::test_layer2_wave8_asset_class_profiles_acceptance -q
python - <<'PY'
from html.parser import HTMLParser
with open('docs/layer2-architecture.html', 'r', encoding='utf-8') as f:
    HTMLParser().feed(f.read())
print('html_parse_ok')
PY
```

Expected: PASS and `html_parse_ok`.

- [ ] **Step 5: Verify registry counts and stale labels**

Run:

```bash
PYTHONPATH=src:blender_addon python - <<'PY'
from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.domains import build_default_registry
specs = build_router().specs()
commands = build_default_registry().names()
required = {'asset_class.list', 'asset_class.describe', 'feedback.quality', 'pipeline.gate_check', 'knowledge.load'}
print('server_specs', len(specs))
print('addon_commands', len(commands))
print('required_specs', required <= {s.name for s in specs})
print('required_commands', required <= set(commands))
print('missing_specs', sorted(required - {s.name for s in specs}))
print('missing_commands', sorted(required - set(commands)))
PY
python - <<'PY'
from pathlib import Path
text = Path('docs/layer2-architecture.html').read_text(encoding='utf-8')
stale = [
    'Waves 1-7',
    'after Layer 2 Wave 7',
    'Wave 8 <span class="tag next-tag"',
    'Asset breadth</span><span>Wave 8',
]
found = [item for item in stale if item in text]
print('stale_labels', found)
raise SystemExit(1 if found else 0)
PY
```

Expected: required specs/commands are `True`, missing lists are empty, stale labels are empty.

- [ ] **Step 6: Commit**

```bash
git add tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "docs: mark Layer 2 Wave 8 built"
```

---

### Task 8: Full Verification and Final Cleanup

**Files:**
- No planned source edits unless verification exposes a concrete failure.

**Interfaces:**
- Consumes all prior tasks.
- Produces final verified Wave 8 branch state.

- [ ] **Step 1: Run full tests**

Run: `pytest -q`

Expected: exit 0.

- [ ] **Step 2: Run strict Blender coverage audit**

Run:

```bash
python - <<'PY'
import json
import subprocess
import sys
cmd = [
    'python', 'scripts/audit_blender_coverage.py',
    '--source', '../blender-source',
    '--json',
    '--fail-on', 'partial',
]
proc = subprocess.run(cmd, capture_output=True, text=True)
print('audit_exit', proc.returncode)
if proc.stdout.strip():
    data = json.loads(proc.stdout)
    print('summary', json.dumps(data.get('summary', {}), sort_keys=True))
    partials = [row for row in data.get('rows', []) if row.get('status') == 'partial']
    missing = [row for row in data.get('rows', []) if row.get('status') == 'missing']
    print('partial_count', len(partials))
    print('missing_count', len(missing))
if proc.stderr.strip():
    print(proc.stderr.strip(), file=sys.stderr)
sys.exit(proc.returncode)
PY
```

Expected:

```text
audit_exit 0
summary {"covered": 58, "missing": 0, "partial": 0}
partial_count 0
missing_count 0
```

- [ ] **Step 3: Run registry exposure check**

Run:

```bash
PYTHONPATH=src:blender_addon python - <<'PY'
from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.domains import build_default_registry
specs = {s.name for s in build_router().specs()}
commands = set(build_default_registry().names())
required = {'asset_class.list', 'asset_class.describe', 'feedback.quality', 'pipeline.start', 'pipeline.gate_check', 'knowledge.load'}
print('required_specs', required <= specs)
print('required_commands', required <= commands)
print('missing_specs', sorted(required - specs))
print('missing_commands', sorted(required - commands))
PY
```

Expected:

```text
required_specs True
required_commands True
missing_specs []
missing_commands []
```

- [ ] **Step 4: Run HTML and whitespace checks**

Run:

```bash
python - <<'PY'
from html.parser import HTMLParser
with open('docs/layer2-architecture.html', 'r', encoding='utf-8') as f:
    HTMLParser().feed(f.read())
print('html_parse_ok')
PY
git diff --check
```

Expected: `html_parse_ok` and no `git diff --check` output.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: only intended uncommitted verification fixes, or a clean tree if every task committed independently.

- [ ] **Step 6: Commit verification fixes if any**

If Step 5 shows files changed because a verification failure was fixed, commit them:

```bash
git add <changed files>
git commit -m "fix: stabilize Layer 2 asset-class profiles"
```

If `git status --short` is empty, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage:
  - Mirrored registries: Task 1.
  - `asset_class.list` and `asset_class.describe`: Task 2.
  - `pipeline.start(asset_class=...)`: Task 3.
  - `feedback.quality(asset_class=...)`: Task 4.
  - `pipeline.gate_check` defaults and gate overrides: Task 5.
  - `knowledge.load(asset_class=...)` and self-critique guidance: Task 6.
  - Architecture diagram: Task 7.
  - Full verification: Task 8.
- Placeholder scan target: no unfinished markers, vague implementation instructions, or references that require reading another task for missing details.
- Type consistency target:
  - Use `asset_class` exactly.
  - Use `profile_version` exactly.
  - Use `effective_defaults` exactly.
  - Use `applied_gate_overrides` exactly.
  - `hard_surface_prop`, `organic_prop`, `generated_cleanup`, `from_scratch_prop` exactly.
