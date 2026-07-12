# Close the Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a real (deterministic) finisher against the real-asset benchmark, delete the FSM control surface and Layer-2 scaffolding (audit §5 Phases 3–4), and add the Godot round-trip import gate + M0 context prose (Phase 5).

**Architecture:** The plan of record is `docs/superpowers/specs/2026-07-03-architecture-audit.md` §5 and the ledger `.superpowers/sdd/lean-rebuild.md`. Three workstreams: (A) a deterministic gate-driven finisher module wired into the existing objective benchmark runner (`--mode agent`), implementing the per-edit checkpoint→act→re-measure→keep-or-revert loop in code; (B) subtractive Phases 3–4 — extract gate definitions out of `core/pipeline.py` (feedback.readiness depends on them), then delete the pipeline FSM domain, craft_workflow, knowledge, modeling_verbs, playbooks, and asset-class prose, every deletion behind green parity + unit tests; (C) Phase 5 — a standalone headless-Godot round-trip import verifier composed into benchmark scoring as a new axis, plus the M0 prose update in `prompts.py`.

**Tech Stack:** Python 3 (pure stdlib in the addon), pytest, hand-rolled MCP kernel (`src/niua_blender_mcp/kernel`), TCP bridge to a visible Blender, `/usr/bin/godot` 4.6.3 for the round-trip gate.

## Global Constraints

- **ZERO niua knowledge in code.** The Blender MCP stays fully standalone. The Godot gate shells out to a generic `godot` binary on a throwaway project — it must NOT import or reference any niua MCP.
- **Every deletion is validated by "objective bench unchanged"** (ledger rule) plus green parity (`tests/test_parity.py`) and the surviving unit suite. Baseline to preserve (from `docs/reports/objective-baseline.md`, real bench): readiness real_character 0.36, real_character_light 0.36, real_creature 0.36, real_multipart 0.24, real_prop 0.28; preservation 1.0 on all 5.
- **Never delete a module while another still imports it.** Deletion order is forced by the import graph: `domains/pipeline.py` imports `core/knowledge.py` + `core/self_critique.py`; `domains/craft_workflow.py` imports `core/pipeline.py`. So: extract gates → delete pipeline domain → delete scaffolding → delete `core/pipeline.py` last.
- **Offline test command:** `NIUA_SKIP_BLENDER=1 python -m pytest -q` from the repo root (Blender smoke tests self-skip). All-green required before every commit.
- **KEEP untouched:** `src/niua_blender_mcp/evals/{stage_gates,gates,scorecard}.py` (gate-floor algebra, audit says KEEP), `src/niua_blender_mcp/manifest/` (codegen input, M5 glue), `domains/asset_class.py` on both sides (the numeric contract surface), all Layer-1 domains, eyes, session checkpoint/revert.
- **Commit style:** one commit per task, conventional-commit subject, `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.

---

### Task 1: Extract gate definitions into `core/gates.py`

`feedback.readiness` imports `check_gates`, `gate_profile`, `stage_gates` from `core/pipeline.py` (feedback.py:43). Those are order-free definitions, not FSM control. Move them to a new `core/gates.py`; `core/pipeline.py` re-exports them (so the FSM keeps working until its deletion task); `feedback.py` retargets.

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/gates.py`
- Create: `tests/core/test_gates.py`
- Modify: `blender_addon/niua_mcp_bridge/core/pipeline.py` (remove moved code, re-import)
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py:43` (import path)
- Modify: `tests/core/test_pipeline_core.py` (gate tests move out)

**Interfaces:**
- Consumes: `core/asset_classes.py` — `get_asset_class(name)`, `apply_gate_overrides(gates, profile, stage)`.
- Produces (later tasks and feedback.py rely on these EXACT signatures):
  - `GATE_PROFILE_BY_STAGE: dict[str, str | None]` — `{"intake": None, "repair": "orientation", "retopo": "retopo", "uv": "uv", "bake": "bake", "material": "material", "optimize": "optimize", "export_preflight": "export_preflight", "exported": None}`
  - `gate_profile(stage: str) -> str | None` (raises `ValueError` on unknown stage)
  - `stage_gates(stage: str, asset_class: str | None = None) -> tuple[list[dict], dict]`
  - `check_gates(metrics: dict, gates: list[dict]) -> dict` (returns `{"gates": [...], "gates_pass": bool}`)

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_gates.py`:

```python
"""Gate DEFINITIONS live in core/gates.py, independent of any pipeline FSM."""

import pytest

from niua_mcp_bridge.core import gates


def test_gate_profile_maps_stages():
    assert gates.gate_profile("repair") == "orientation"
    assert gates.gate_profile("retopo") == "retopo"
    assert gates.gate_profile("intake") is None
    with pytest.raises(ValueError):
        gates.gate_profile("nonsense")


def test_stage_gates_applies_asset_class_overrides():
    base, applied = gates.stage_gates("retopo")
    assert {g["path"] for g in base} == {
        "topology.quad_ratio", "topology.ngons", "topology.non_manifold_edges"
    }
    assert applied == {}
    organic, applied = gates.stage_gates("retopo", asset_class="organic_prop")
    quad = next(g for g in organic if g["path"] == "topology.quad_ratio")
    assert quad["value"] == 0.85
    assert "retopo" in applied


def test_check_gates_evaluates_paths():
    metrics = {"topology": {"quad_ratio": 0.99, "ngons": 0, "non_manifold_edges": 3}}
    out = gates.check_gates(metrics, gates.stage_gates("retopo")[0])
    assert out["gates_pass"] is False
    by_path = {g["path"]: g for g in out["gates"]}
    assert by_path["topology.quad_ratio"]["pass"] is True
    assert by_path["topology.non_manifold_edges"]["pass"] is False
    assert by_path["topology.non_manifold_edges"]["actual"] == 3


def test_missing_metric_fails_closed():
    out = gates.check_gates({}, gates.stage_gates("uv")[0])
    assert out["gates_pass"] is False
    assert all(g["actual"] is None and g["pass"] is False for g in out["gates"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/core/test_gates.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'niua_mcp_bridge.core.gates'` (or ImportError).

- [ ] **Step 3: Create `blender_addon/niua_mcp_bridge/core/gates.py`**

Move (cut, don't copy) from `core/pipeline.py`: `_OPS`, `_GATES`, `_dig`, `check_gates`, plus new `GATE_PROFILE_BY_STAGE`, `gate_profile`, `stage_gates` (bodies below are the existing pipeline.py logic with the `_STAGES` lookup replaced by the dict):

```python
"""Objective gate DEFINITIONS: the order-free numeric contract for game-readiness.

This is the load-bearing organ extracted from the deleted pipeline FSM (architecture
audit §2: "KEEP + PROMOTE"). `feedback.readiness` aggregates these groups in NO order;
nothing here stores state, sequences stages, or blocks anything.
"""

from __future__ import annotations

from copy import deepcopy
import operator
from typing import Any

from . import asset_classes

_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "<": operator.lt, ">": operator.gt}

#: Gate-group name -> gate-profile name (None = no objective gates for that group).
GATE_PROFILE_BY_STAGE: dict[str, str | None] = {
    "intake": None,
    "repair": "orientation",
    "retopo": "retopo",
    "uv": "uv",
    "bake": "bake",
    "material": "material",
    "optimize": "optimize",
    "export_preflight": "export_preflight",
    "exported": None,
}

_GATES = {
    # ... paste the _GATES dict from core/pipeline.py lines 25-66 VERBATIM ...
}


def gate_profile(stage: str) -> str | None:
    try:
        return GATE_PROFILE_BY_STAGE[stage]
    except KeyError as exc:
        raise ValueError(f"unknown pipeline stage: {stage}") from exc


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


def _dig(metrics: dict[str, Any], path: str) -> Any:
    cur: Any = metrics
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def check_gates(metrics: dict[str, Any], gates: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    all_pass = True
    for gate in gates:
        actual = _dig(metrics, gate["path"])
        fn = _OPS.get(gate["op"])
        ok = bool(actual is not None and fn is not None and fn(actual, gate["value"]))
        all_pass = all_pass and ok
        results.append({"path": gate["path"], "op": gate["op"], "value": gate["value"],
                        "actual": actual, "pass": ok})
    return {"gates": results, "gates_pass": all_pass}
```

In `core/pipeline.py`: delete the moved `_OPS`/`_GATES`/`_dig`/`check_gates`/`gate_profile`/`stage_gates` definitions and add at the top (temporary shim, dies with the file in Task 4):

```python
from .gates import check_gates, gate_profile, stage_gates  # noqa: F401 - re-export until FSM deletion
```

In `domains/feedback.py` line 43 change to:

```python
from ..core.gates import check_gates, gate_profile, stage_gates  # gate DEFINITIONS, not FSM control
```

Also update the two docstring mentions of `core/pipeline.{stage_gates,...}` in feedback.py (lines 21 and 203) to say `core/gates.{stage_gates,check_gates,gate_profile}`.

Move any tests in `tests/core/test_pipeline_core.py` that exercise ONLY `check_gates`/`stage_gates`/`gate_profile` into `tests/core/test_gates.py` (adjust imports to `core.gates`); leave FSM tests (`start`/`advance`/`rollback_pointer`/`status`) in place — they die in Task 2/4.

- [ ] **Step 4: Run the full offline suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS (754+4 new, minus any moved duplicates). Zero failures.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/gates.py blender_addon/niua_mcp_bridge/core/pipeline.py \
        blender_addon/niua_mcp_bridge/domains/feedback.py tests/core/test_gates.py tests/core/test_pipeline_core.py
git commit -m "refactor: extract order-free gate definitions to core/gates.py (pre-FSM-deletion)"
```

---

### Task 2: Delete the pipeline FSM tool surface (Phase 3)

Deletes the control machine's tools on both sides plus `self_critique`. `core/pipeline.py` itself SURVIVES this task (still imported by `domains/craft_workflow.py`) — it dies in Task 4.

**Files:**
- Delete: `blender_addon/niua_mcp_bridge/domains/pipeline.py`
- Delete: `src/niua_blender_mcp/domains/pipeline.py`
- Delete: `blender_addon/niua_mcp_bridge/core/self_critique.py`
- Delete: `tests/domains/test_pipeline.py`, `tests/core/test_self_critique.py`
- Modify: `tests/test_smoke_headless.py` (remove FSM acceptance tests)
- Modify: `.superpowers/sdd/lean-rebuild.md` (progress note)

**Interfaces:**
- Consumes: Task 1's `core/gates.py` (feedback.py must already be retargeted, or these deletes break readiness).
- Produces: a tool surface with NO `pipeline.*` names. Parity stays green because BOTH sides lose the same 6 commands (`pipeline.start/status/gate_check/advance/rollback/self_critique`) — auto-discovery means no registry edits.

- [ ] **Step 1: Confirm nothing outside the death-list imports the death-list**

Run: `grep -rn "domains.pipeline\|domains import pipeline\|self_critique\|pipeline\.start\|pipeline\.advance\|pipeline\.gate_check\|pipeline\.rollback\|pipeline\.status" --include="*.py" src blender_addon scripts tests | grep -v "core/pipeline\|core.pipeline\|test_pipeline\|test_self_critique\|smoke"`
Expected: only hits inside the files being deleted (and `domains/craft_workflow.py`'s `core.pipeline` import, which survives until Task 4). If anything else shows up, STOP and report — don't delete.

- [ ] **Step 2: Delete the files**

```bash
git rm blender_addon/niua_mcp_bridge/domains/pipeline.py src/niua_blender_mcp/domains/pipeline.py \
       blender_addon/niua_mcp_bridge/core/self_critique.py \
       tests/domains/test_pipeline.py tests/core/test_self_critique.py
```

- [ ] **Step 3: Remove the FSM smoke tests**

In `tests/test_smoke_headless.py` delete these whole test functions (and any helper used only by them):
- `test_layer2_wave2_pipeline_spine_acceptance` (~line 741)
- `test_layer2_wave3_self_critique_acceptance` (~line 1042)
- any other function that calls a `pipeline.*` tool — find with `grep -n '"pipeline\.' tests/test_smoke_headless.py`.

- [ ] **Step 4: Prune the FSM tests from `tests/core/test_pipeline_core.py`**

Delete the tests covering `start`/`advance`/`rollback_pointer`/`record_gate`/`status`/`get_state`/`reset` — everything that touches `_STORE`. If nothing remains in the file, `git rm` it (its gate tests moved in Task 1). If a few tests remain that only exercise `stage_gates`-via-pipeline re-export, rewrite their import to `core.gates` and move them to `tests/core/test_gates.py`.

- [ ] **Step 5: Full suite + parity**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q && NIUA_SKIP_BLENDER=1 python -m pytest tests/test_parity.py -q`
Expected: PASS. If parity fails it will name a one-sided command — fix by deleting the missed side, never by re-adding.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat!: delete pipeline FSM tool surface (Phase 3) — gates live on in core/gates.py + feedback.readiness"
```

---

### Task 3: Delete craft_workflow, knowledge, modeling_verbs, playbooks (Phase 4a)

The disproven scaffolding: recipe registry, knowledge packs, composite form verbs, playbooks prose.

**Files:**
- Delete (addon): `domains/craft_workflow.py`, `domains/knowledge.py`, `domains/modeling_verbs.py`, `core/craft_workflows.py`, `core/knowledge.py`
- Delete (server): `domains/craft_workflow.py`, `domains/knowledge.py`, `domains/modeling_verbs.py`, `craft_workflows.py`, `knowledge/` (whole package), `playbooks/` (whole package)
- Delete (tests): `tests/domains/test_craft_workflow.py`, `tests/domains/test_knowledge.py`, `tests/domains/test_modeling_verbs.py`, `tests/core/test_knowledge.py`, `tests/test_craft_workflows.py`, `tests/test_playbooks.py`
- Modify: `tests/test_smoke_headless.py` (scaffolding acceptance tests)

**Interfaces:**
- Consumes: Task 2 must be done (`domains/pipeline.py` — the other importer of `core/knowledge.py` — is already gone).
- Produces: tool surface with no `craft_workflow.*`, `knowledge.*`, or `model.*` composite verbs. `capabilities.*`, `asset_class.*` and all Layer-1 verbs untouched.

- [ ] **Step 1: Confirm the import graph is clear**

Run: `grep -rn "craft_workflows\|core import knowledge\|core.knowledge\|playbooks\|niua_blender_mcp.knowledge" --include="*.py" src blender_addon scripts tests | grep -v test_smoke`
Expected: hits only inside the death-list files themselves. Anything else → STOP and report.

- [ ] **Step 2: Delete**

```bash
git rm blender_addon/niua_mcp_bridge/domains/craft_workflow.py blender_addon/niua_mcp_bridge/domains/knowledge.py \
       blender_addon/niua_mcp_bridge/domains/modeling_verbs.py blender_addon/niua_mcp_bridge/core/craft_workflows.py \
       blender_addon/niua_mcp_bridge/core/knowledge.py \
       src/niua_blender_mcp/domains/craft_workflow.py src/niua_blender_mcp/domains/knowledge.py \
       src/niua_blender_mcp/domains/modeling_verbs.py src/niua_blender_mcp/craft_workflows.py
git rm -r src/niua_blender_mcp/knowledge src/niua_blender_mcp/playbooks
git rm tests/domains/test_craft_workflow.py tests/domains/test_knowledge.py tests/domains/test_modeling_verbs.py \
       tests/core/test_knowledge.py tests/test_craft_workflows.py tests/test_playbooks.py
```

- [ ] **Step 3: Sweep the smoke tests**

In `tests/test_smoke_headless.py` delete every test function that calls `craft_workflow.*`, `knowledge.*`, or `model.retopo_quads`/`model.bevel_edges`/`model.recess_panels`/`model.panel_detail_pass`/`model.mirror_x`/`model.solidify_shell` (grep: `grep -n '"craft_workflow\.\|"knowledge\.\|"model\.' tests/test_smoke_headless.py`). Known: `test_layer2_wave9a_craft_workflow_acceptance` (~line 927) and the knowledge.load acceptance around line 902.

- [ ] **Step 4: Full suite + parity**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS. Also check `tests/test_blender_coverage_audit.py` and `tests/test_autodiscovery.py` still pass (they discover domains dynamically; deletion should be invisible — if one hardcodes a deleted name, delete that assertion line).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat!: delete craft_workflow + knowledge packs + composite form verbs + playbooks (Phase 4)"
```

---

### Task 4: Delete `core/pipeline.py`; strip asset-class prose (Phase 4b)

Nothing imports `core/pipeline.py` now except its own tests and the Task 1 shim. Kill it, then reduce asset classes to the pure numeric contract.

**Files:**
- Delete: `blender_addon/niua_mcp_bridge/core/pipeline.py`, `tests/core/test_pipeline_core.py` (if still present)
- Modify: `blender_addon/niua_mcp_bridge/core/asset_classes.py` (strip prose, base+deltas, drop `state` param)
- Modify: `src/niua_blender_mcp/asset_classes.py` (same treatment — it mirrors)
- Modify: `blender_addon/niua_mcp_bridge/core/preservation_ledger.py` (stale comment references `core/pipeline._STORE`)
- Modify: `tests/test_asset_classes.py` and any addon-side asset-class tests (drop prose assertions)

**Interfaces:**
- Consumes: `asset_classes.apply_asset_class_defaults(payload)` — after this task the `state` parameter is GONE (its only caller was the deleted `pipeline.gate_check`).
- Produces: `get_asset_class(name) -> dict` with keys exactly `{id, profile_version, label, summary, defaults, gate_overrides}` — NO `stage_targets`, NO `guidance`. `ASSET_CLASS_IDS` unchanged (all 4 ids survive; server Enum specs depend on them).

- [ ] **Step 1: Verify then delete core/pipeline.py**

Run: `grep -rn "core.pipeline\|core import pipeline" --include="*.py" src blender_addon scripts tests`
Expected: zero hits outside `core/pipeline.py` itself / its test. Then:

```bash
git rm blender_addon/niua_mcp_bridge/core/pipeline.py
git rm -f tests/core/test_pipeline_core.py
```

Fix the comment in `core/preservation_ledger.py` line ~6: replace the sentence referencing `core/pipeline._STORE` with "This ledger is a passive per-object scratchpad; it holds no stage/order/progress state."

- [ ] **Step 2: Write the failing test for the numeric-only contract**

Add to `tests/test_asset_classes.py`:

```python
def test_profiles_are_numbers_only_no_prose():
    for profile in asset_classes.list_asset_classes():
        assert "stage_targets" not in profile, profile["id"]
        assert "guidance" not in profile, profile["id"]
        assert set(profile) == {"id", "profile_version", "label", "summary",
                                "defaults", "gate_overrides"}


def test_apply_defaults_takes_no_pipeline_state():
    import inspect
    sig = inspect.signature(asset_classes.apply_asset_class_defaults)
    assert list(sig.parameters) == ["payload"]
```

(mirror the same two tests in the addon-side asset-class test file if one exists under `tests/core/` or `tests/domains/`; check with `grep -rln "asset_classes" tests/`)

- [ ] **Step 3: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_asset_classes.py -q`
Expected: FAIL on both new tests.

- [ ] **Step 4: Implement in BOTH `asset_classes.py` copies**

1. Delete every `stage_targets` and `guidance` key from `_PROFILES`.
2. Collapse to base + sparse deltas — replace the 4 near-duplicate dicts:

```python
_BASE_DEFAULTS = {
    "triangle_budget": 5000, "material_budget": 4, "texture_budget": 8,
    "min_lods": 1, "max_lod_triangle_ratio": 0.75, "max_lod_bounds_delta": 0.10,
    "min_collision_hulls": 1, "max_collision_oversize_ratio": 0.50, "max_texture_size": 2048,
}

def _profile(pid, label, summary, defaults_delta=None, gate_overrides=None):
    return {
        "id": pid, "profile_version": 1, "label": label, "summary": summary,
        "defaults": {**_BASE_DEFAULTS, **(defaults_delta or {})},
        "gate_overrides": gate_overrides or {},
    }

_PROFILES = {
    "hard_surface_prop": _profile(
        "hard_surface_prop", "Hard-surface prop",
        "Structured hard-surface game prop with clean quad topology and tight collision."),
    "organic_prop": _profile(
        "organic_prop", "Organic prop",
        "Organic or sculpt-derived prop where silhouette preservation is more important than perfect quads.",
        {"triangle_budget": 8000, "material_budget": 3, "max_lod_triangle_ratio": 0.80,
         "max_lod_bounds_delta": 0.18, "max_collision_oversize_ratio": 0.75},
        {"retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.85}},
         "uv": {"uv.stretch_ratio": {"op": "<=", "value": 2.5}}}),
    "generated_cleanup": _profile(
        "generated_cleanup", "Generated cleanup",
        "Cleanup pass for generated or scanned meshes that need stricter retopo and UV gates.",
        {"triangle_budget": 6000, "max_lod_triangle_ratio": 0.65, "max_lod_bounds_delta": 0.12},
        {"retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.98}},
         "uv": {"uv.stretch_ratio": {"op": "<=", "value": 1.75}}}),
    "from_scratch_prop": _profile(
        "from_scratch_prop", "From-scratch prop",
        "Freshly authored prop with tighter budgets because topology and materials are controllable from the start.",
        {"triangle_budget": 4000, "material_budget": 3, "texture_budget": 6}),
}
```

(The numeric values above are copied verbatim from the current file — a delta appears ONLY where a profile differs from `_BASE_DEFAULTS`. Cross-check each number against the pre-edit file before committing; a silently changed threshold is a benchmark change.)

3. In the ADDON copy only, drop the `state` plumbing: delete `_class_from_payload_or_state` and change:

```python
def apply_asset_class_defaults(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = payload.get("asset_class")
    asset_class = raw if isinstance(raw, str) and raw else DEFAULT_ASSET_CLASS
    defaulted = not (isinstance(raw, str) and raw)
    profile = get_asset_class(asset_class)
    ...  # rest of the body unchanged from today
```

Check the server copy (`src/niua_blender_mcp/asset_classes.py`) for the same prose keys and `state` param and apply the identical treatment (read it first — it may already differ).

4. Sweep prose assertions from existing tests: `grep -rn "stage_targets\|guidance" tests/` and delete those assertion lines/tests.

- [ ] **Step 5: Run the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat!: delete core/pipeline.py FSM store; asset classes collapse to numeric contract (base + deltas, no prose)"
```

---

### Task 5: The deterministic finisher

The reference finishing agent: reads the order-free readiness gates, applies the smallest standard fix per failing group, wraps EVERY fix in checkpoint → act → re-measure (readiness + preservation) → keep-iff-not-worse-else-revert. Deterministic so benchmark deltas measure the TOOL, not a model's mood.

**Files:**
- Create: `src/niua_blender_mcp/evals/finisher.py`
- Create: `tests/evals/test_finisher.py`

**Interfaces:**
- Consumes: live bridge tools `feedback.readiness`, `feedback.preservation`, `feedback.quality`, `session.checkpoint`, `session.revert`, `scene.info`, `object.delete`, and the fix verbs listed in `TOOLS_USED` below. `BridgeError` from `niua_blender_mcp.bridge`.
- Produces: `finish(bridge, subject: str, item: dict) -> dict` — EXACTLY the signature `scripts/run_objective_benchmark.py` `--finisher` expects. Module-level `TOOLS_USED: set[str]` and `MOVES: list[tuple[str, tuple[str, ...], Callable]]` (tests + the runner guard consume these).

- [ ] **Step 1: Write the failing tests**

Create `tests/evals/test_finisher.py`:

```python
"""The finisher's accept/revert loop, offline: a FakeBridge scripts tool responses."""

from __future__ import annotations

import pytest

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.domains import build_router
from niua_blender_mcp.evals import finisher


def _readiness(score, failing=()):
    per_gate = [{"path": p, "op": "==", "value": True, "actual": False, "pass": False}
                for p in failing]
    per_gate.append({"path": "always.pass", "op": "==", "value": True, "actual": True, "pass": True})
    return {"readiness": score, "per_gate": per_gate}


class FakeBridge:
    """Scripted bridge: feedback.readiness pops from a queue (last repeats); everything else logs."""

    def __init__(self, readiness_queue, preservation=1.0, fail_tools=()):
        self.queue = list(readiness_queue)
        self.preservation = preservation
        self.fail_tools = set(fail_tools)
        self.calls = []

    def call(self, tool, payload):
        self.calls.append((tool, payload))
        if tool in self.fail_tools:
            raise BridgeError("internal_error", f"{tool} exploded")
        if tool == "feedback.readiness":
            return self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if tool == "feedback.preservation":
            return {"available": True, "preservation": self.preservation}
        if tool == "feedback.quality":
            return {"topology": {"tris": 100000},
                    "asset_class": {"effective_defaults": {"triangle_budget": 5000}}}
        if tool == "scene.info":
            return {"objects": [{"name": "subject", "type": "MESH"}]}
        return {}

    def tools(self, *names):
        return [c for c in self.calls if c[0] in names]


ITEM = {"id": "t", "asset_class": "hard_surface_prop"}


def test_move_skipped_when_its_gates_pass():
    bridge = FakeBridge([_readiness(1.0)])
    out = finisher.finish(bridge, "subject", ITEM)
    assert out["moves"] == []
    assert bridge.tools("session.checkpoint") == []


def test_improving_move_is_kept():
    # uv gates failing; after the move readiness rises 0.5 -> 0.7
    seq = [_readiness(0.5, ["uv.has_uvs"])] * 3 + [_readiness(0.7)]
    bridge = FakeBridge(seq)
    out = finisher.finish(bridge, "subject", ITEM)
    kept = [m for m in out["moves"] if m["move"] == "uv_unwrap"]
    assert kept and kept[0]["kept"] is True
    assert bridge.tools("session.revert") == []
    assert bridge.tools("uv.smart_unwrap") and bridge.tools("uv.pack_islands")


def test_regressing_move_is_reverted():
    seq = [_readiness(0.5, ["uv.has_uvs"])] * 3 + [_readiness(0.3, ["uv.has_uvs"])]
    bridge = FakeBridge(seq)
    out = finisher.finish(bridge, "subject", ITEM)
    move = next(m for m in out["moves"] if m["move"] == "uv_unwrap")
    assert move["kept"] is False
    reverts = bridge.tools("session.revert")
    assert reverts and reverts[0][1]["label"] == "finisher:uv_unwrap"


def test_harm_below_preservation_floor_reverts_even_if_readiness_rose():
    seq = [_readiness(0.5, ["engine.within_triangle_budget"])] * 3 + [_readiness(0.9)]
    bridge = FakeBridge(seq, preservation=0.5)
    out = finisher.finish(bridge, "subject", ITEM)
    move = next(m for m in out["moves"] if m["move"] == "decimate_to_budget")
    assert move["kept"] is False
    assert bridge.tools("session.revert")


def test_erroring_move_reverts_and_continues():
    seq = [_readiness(0.5, ["uv.has_uvs", "scale.transform_applied"])]
    bridge = FakeBridge(seq, fail_tools={"uv.smart_unwrap"})
    out = finisher.finish(bridge, "subject", ITEM)
    errored = next(m for m in out["moves"] if m["move"] == "uv_unwrap")
    assert errored["kept"] is False and "error" in errored
    # the later transform move still ran
    assert bridge.tools("object.transform_apply")


def test_every_finisher_tool_is_registered():
    known = {("capabilities.invoke" if s.tier == "generated" else s.command)
             for s in build_router().specs()}
    missing = finisher.TOOLS_USED - known
    assert not missing, sorted(missing)
```

- [ ] **Step 2: Run to verify failure**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/evals/test_finisher.py -q`
Expected: FAIL — no module `niua_blender_mcp.evals.finisher`.

- [ ] **Step 3: Implement `src/niua_blender_mcp/evals/finisher.py`**

```python
"""Deterministic gate-driven finisher: the benchmark's reference finishing agent.

Wired into scripts/run_objective_benchmark.py via
  --mode agent --finisher niua_blender_mcp.evals.finisher:finish

Reads the order-free readiness gates and, for each failing gate group, applies the
smallest standard fix — every fix wrapped in the per-edit accept/revert loop:
session.checkpoint -> act -> re-measure readiness + preservation -> keep iff readiness
did not drop AND preservation (when measured) stays above the floor, else session.revert.
Moves that create helper objects (LODs, collision) get those objects deleted on revert.
No LLM decides anything here, so benchmark deltas measure the TOOL surface, not the
model driving it. Do-no-harm follows measure-and-flag: an UNMEASURED preservation never
blocks a move (a headless run must not deadlock the finisher), a measured drop below
the floor always reverts it.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from ..bridge import BridgeError

PRESERVATION_FLOOR = 0.85
_EPS = 1e-9


def _fmt(x: Any) -> str:
    return f"{x:.3f}" if isinstance(x, (int, float)) else "?"


def _log(item_id: str, msg: str) -> None:
    print(f"    [finisher:{item_id}] {msg}", file=sys.stderr)


def _payload(subject: str, asset_class: str | None) -> dict:
    return {"object": subject, "asset_class": asset_class} if asset_class else {"object": subject}


def _readiness(bridge: Any, subject: str, asset_class: str | None) -> dict:
    return bridge.call("feedback.readiness", _payload(subject, asset_class))


def _failing(readiness: dict, *paths: str) -> bool:
    by_path = {g["path"]: g for g in (readiness or {}).get("per_gate", [])}
    return any(p in by_path and not by_path[p]["pass"] for p in paths)


def _preservation_ok(bridge: Any, subject: str) -> tuple[bool, float | None]:
    """Measured-and-below-floor is the only failure; unmeasured is not harm."""
    try:
        pres = bridge.call("feedback.preservation", {"object": subject})
    except BridgeError:
        return True, None
    score = pres.get("preservation")
    if not pres.get("available") or score is None:
        return True, None
    return score >= PRESERVATION_FLOOR, score


def _scene_objects(bridge: Any) -> set[str]:
    return {o["name"] for o in bridge.call("scene.info", {}).get("objects", [])}


# ---- the moves (senior finishing order; each fires only on its failing gates) --------

def _select_all(bridge: Any, subject: str) -> None:
    bridge.call("mesh.select_all", {"object": subject, "action": "SELECT"})


def _repair(bridge: Any, subject: str, info: dict) -> None:
    _select_all(bridge, subject)
    bridge.call("mesh.remove_doubles", {"object": subject})
    bridge.call("mesh.recalc_normals", {"object": subject})


def _decimate_to_budget(bridge: Any, subject: str, info: dict) -> None:
    q = bridge.call("feedback.quality", _payload(subject, info["asset_class"]))
    tris = int(q.get("topology", {}).get("tris") or 0)
    budget = int(q.get("asset_class", {}).get("effective_defaults", {}).get("triangle_budget") or 0)
    if tris <= 0 or budget <= 0 or budget >= tris:
        return
    ratio = max(0.01, min(1.0, budget / tris))
    bridge.call("modifiers.add", {"object": subject, "type": "DECIMATE", "name": "niua_decimate"})
    bridge.call("modifiers.set", {"object": subject, "name": "niua_decimate",
                                  "property": "ratio", "value": str(ratio)})
    bridge.call("modifiers.apply", {"object": subject, "name": "niua_decimate"})


def _tris_to_quads(bridge: Any, subject: str, info: dict) -> None:
    _select_all(bridge, subject)
    bridge.call("mesh.tris_to_quads", {"object": subject})


def _uv_unwrap(bridge: Any, subject: str, info: dict) -> None:
    _select_all(bridge, subject)
    bridge.call("uv.smart_unwrap", {"object": subject})
    bridge.call("uv.pack_islands", {"object": subject})


def _pbr_maps(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("shading.prepare_pbr_maps", {"object": subject})


def _lod(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("object.lod_create", {"object": subject, "ratio": 0.5, "apply": True})


def _collision(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("object.collision_proxy_create", {"object": subject})
    bridge.call("object.collision_hulls_create", {"object": subject})


def _apply_transform(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("object.transform_apply", {"object": subject})


#: (name, gate paths that trigger it, apply)
MOVES: list[tuple[str, tuple[str, ...], Callable[[Any, str, dict], None]]] = [
    ("repair", ("orientation.degenerate_faces", "orientation.inward_facing_faces",
                "topology.non_manifold_edges"), _repair),
    ("decimate_to_budget", ("engine.within_triangle_budget",), _decimate_to_budget),
    ("tris_to_quads", ("topology.quad_ratio", "topology.ngons"), _tris_to_quads),
    ("uv_unwrap", ("uv.has_uvs", "uv.overlap_detected", "uv.out_of_bounds_loops",
                   "uv.stretch_ratio"), _uv_unwrap),
    ("pbr_maps", ("material.pbr_maps_present", "material.bake_maps_present",
                  "material.data_maps_non_color", "material.textures_within_size",
                  "material.atlas_ready"), _pbr_maps),
    ("lod", ("engine.has_lods", "engine.lod_triangle_reduction_ok",
             "engine.lod_silhouette_preserved"), _lod),
    ("collision", ("engine.has_collision_proxy", "engine.has_collision_hulls",
                   "engine.collision_bounds_valid"), _collision),
    ("apply_transform", ("scale.transform_applied",), _apply_transform),
]

#: Every tool name this module can call (checked registered by tests + the runner guard).
TOOLS_USED = {
    "feedback.readiness", "feedback.preservation", "feedback.quality",
    "session.checkpoint", "session.revert", "scene.info", "object.delete",
    "mesh.select_all", "mesh.remove_doubles", "mesh.recalc_normals", "mesh.tris_to_quads",
    "modifiers.add", "modifiers.set", "modifiers.apply",
    "uv.smart_unwrap", "uv.pack_islands",
    "shading.prepare_pbr_maps",
    "object.lod_create", "object.collision_proxy_create", "object.collision_hulls_create",
    "object.transform_apply",
}


def _revert(bridge: Any, subject: str, label: str, objs_before: set[str]) -> None:
    strays = sorted(_scene_objects(bridge) - objs_before)
    if strays:
        bridge.call("object.delete", {"objects": ",".join(strays)})
    bridge.call("session.revert", {"object": subject, "label": label})


def finish(bridge: Any, subject: str, item: dict) -> dict:
    """Runner entrypoint: finish `subject` in place; returns a per-move report."""
    asset_class = item.get("asset_class")
    item_id = str(item.get("id", subject))
    info = {"asset_class": asset_class}
    moves_report: list[dict] = []
    start = _readiness(bridge, subject, asset_class)

    for name, paths, apply_move in MOVES:
        before = _readiness(bridge, subject, asset_class)
        if not _failing(before, *paths):
            continue
        label = f"finisher:{name}"
        bridge.call("session.checkpoint", {"object": subject, "label": label})
        objs_before = _scene_objects(bridge)
        try:
            apply_move(bridge, subject, info)
        except BridgeError as exc:
            _revert(bridge, subject, label, objs_before)
            moves_report.append({"move": name, "kept": False, "error": str(exc)[:120]})
            _log(item_id, f"{name}: ERROR {str(exc)[:80]} -> reverted")
            continue
        after = _readiness(bridge, subject, asset_class)
        r_before = before.get("readiness") or 0.0
        r_after = after.get("readiness") or 0.0
        pres_ok, pres = _preservation_ok(bridge, subject)
        kept = (r_after >= r_before - _EPS) and pres_ok
        if not kept:
            _revert(bridge, subject, label, objs_before)
        moves_report.append({"move": name, "kept": kept,
                             "readiness_before": before.get("readiness"),
                             "readiness_after": after.get("readiness"),
                             "preservation": pres})
        _log(item_id, f"{name}: {_fmt(before.get('readiness'))} -> {_fmt(after.get('readiness'))} "
                      f"pres={_fmt(pres)} {'KEPT' if kept else 'REVERTED'}")

    final = _readiness(bridge, subject, asset_class)
    return {"readiness_start": start.get("readiness"),
            "readiness_final": final.get("readiness"), "moves": moves_report}
```

Implementation notes (verify, don't trust): the payload key/param names above were read from the server SPECS on 2026-07-10 (`modifiers.set` uses `name`/`property`/`value` as strings; `object.lod_create` has `ratio`+`apply`; `session.revert` takes `object`+`label`). If `test_every_finisher_tool_is_registered` passes but a param name is wrong, the server-side `validate()` will reject it at live-run time — cross-check each payload against the specs in `src/niua_blender_mcp/domains/{mesh,modifiers,uv,shading,objects,session}.py` before finishing this task. Check `mesh.select_all`'s exact param names (`action`?) in `src/niua_blender_mcp/domains/mesh.py` and adjust `_select_all` if needed.

- [ ] **Step 4: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/evals/test_finisher.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Full suite, then commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`

```bash
git add src/niua_blender_mcp/evals/finisher.py tests/evals/test_finisher.py
git commit -m "feat: deterministic gate-driven finisher (per-move checkpoint/measure/keep-or-revert)"
```

---

### Task 6: Godot round-trip verifier (standalone)

Ground truth for "game-ready": does the exported .glb import clean into a headless Godot? Pure subprocess module, zero MCP/niua dependency, degrades to `{"available": False}` without a godot binary.

**Files:**
- Create: `src/niua_blender_mcp/evals/godot_roundtrip.py`
- Create: `tests/evals/test_godot_roundtrip.py`

**Interfaces:**
- Consumes: nothing from this codebase (stdlib only: `os`, `shutil`, `subprocess`, `tempfile`).
- Produces: `verify_gltf_import(glb_path: str, godot_bin: str = "godot", timeout: float = 240.0) -> dict` with keys: `available: bool` (+`reason` when False); when available: `ok: bool`, `returncode: int | None`, `errors: list[str]`, `sidecar: bool`, `artifacts: list[str]`, `log_tail: list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/evals/test_godot_roundtrip.py`:

```python
"""Godot round-trip verifier: unit tests fake the binary; one integration test uses a real godot."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from niua_blender_mcp.evals import godot_roundtrip as rt


def test_unavailable_without_godot_binary(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: None)
    out = rt.verify_gltf_import(str(glb))
    assert out == {"available": False, "reason": "godot binary not found: godot"}


def test_unavailable_without_export_file(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    out = rt.verify_gltf_import("/nope/missing.glb")
    assert out["available"] is False and "missing" in out["reason"]


def _fake_run(rc=0, out="", err="", make_artifacts=True):
    def run(cmd, capture_output, text, timeout):
        proj = cmd[cmd.index("--path") + 1]
        if make_artifacts:
            Path(proj, "asset.glb.import").write_text("[remap]")
            imported = Path(proj, ".godot", "imported")
            imported.mkdir(parents=True)
            (imported / "asset.glb-abc123.scn").write_bytes(b"scn")
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)
    return run


def test_clean_import_is_ok(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    monkeypatch.setattr(subprocess, "run", _fake_run(rc=0, out="importing asset.glb\n"))
    out = rt.verify_gltf_import(str(glb))
    assert out["available"] is True and out["ok"] is True
    assert out["errors"] == [] and out["sidecar"] is True


def test_error_lines_fail_the_import(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    monkeypatch.setattr(subprocess, "run",
                        _fake_run(rc=0, err="ERROR: glTF: buffer overrun in asset.glb\n"))
    out = rt.verify_gltf_import(str(glb))
    assert out["ok"] is False and any("buffer overrun" in e for e in out["errors"])


def test_missing_artifacts_fail_the_import(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    monkeypatch.setattr(subprocess, "run", _fake_run(rc=0, make_artifacts=False))
    out = rt.verify_gltf_import(str(glb))
    assert out["ok"] is False


def test_timeout_is_a_measured_failure(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")

    def boom(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)
    monkeypatch.setattr(subprocess, "run", boom)
    out = rt.verify_gltf_import(str(glb), timeout=5)
    assert out["available"] is True and out["ok"] is False
    assert any("timed out" in e for e in out["errors"])


_FIXTURES = Path(__file__).resolve().parents[2] / "src/niua_blender_mcp/evals/benchmark/assets"


@pytest.mark.skipif(shutil.which("godot") is None, reason="no godot binary")
@pytest.mark.skipif(not any(_FIXTURES.glob("*.glb")) if _FIXTURES.is_dir() else True,
                    reason="no local .glb fixture (git-ignored)")
def test_real_godot_imports_a_real_fixture():
    glb = sorted(_FIXTURES.glob("*.glb"))[0]
    out = rt.verify_gltf_import(str(glb), timeout=300)
    assert out["available"] is True
    assert out["ok"] is True, out  # a known-good generator asset must import clean
```

- [ ] **Step 2: Run to verify failure**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/evals/test_godot_roundtrip.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `src/niua_blender_mcp/evals/godot_roundtrip.py`**

```python
"""Godot round-trip import gate: the apex ground truth for "game-ready".

Shells out to a generic `godot` binary (any 4.x) with --headless --import on a
throwaway one-file project containing just the exported .glb. Standalone by design:
no engine-project knowledge, no MCP dependency — the only question answered is
"does this export import clean?" Degrades honestly: no godot binary or no export
file -> {"available": False} (UNMEASURED, never a fake pass or fail); a hung or
erroring import -> {"available": True, "ok": False} (a measured failure).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

_PROJECT_GODOT = 'config_version=5\n\n[application]\nconfig/name="niua_roundtrip"\n'


def verify_gltf_import(glb_path: str, godot_bin: str = "godot", timeout: float = 240.0) -> dict:
    if shutil.which(godot_bin) is None:
        return {"available": False, "reason": f"godot binary not found: {godot_bin}"}
    if not os.path.isfile(glb_path):
        return {"available": False, "reason": f"export file missing: {glb_path}"}
    with tempfile.TemporaryDirectory(prefix="niua_godot_rt_") as proj:
        with open(os.path.join(proj, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write(_PROJECT_GODOT)
        asset = os.path.join(proj, "asset.glb")
        shutil.copyfile(glb_path, asset)
        try:
            run = subprocess.run(
                [godot_bin, "--headless", "--path", proj, "--import"],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"available": True, "ok": False, "returncode": None,
                    "errors": [f"import timed out after {timeout:.0f}s"],
                    "sidecar": False, "artifacts": [], "log_tail": []}
        log = (run.stdout or "") + "\n" + (run.stderr or "")
        lines = [line.strip() for line in log.splitlines() if line.strip()]
        errors = [line for line in lines if line.startswith("ERROR") or "SCRIPT ERROR" in line]
        sidecar = os.path.isfile(asset + ".import")
        imported_dir = os.path.join(proj, ".godot", "imported")
        artifacts = sorted(os.listdir(imported_dir)) if os.path.isdir(imported_dir) else []
        ok = (run.returncode == 0 and not errors and sidecar
              and any(a.startswith("asset.glb") for a in artifacts))
        return {"available": True, "ok": ok, "returncode": run.returncode,
                "errors": errors[:10], "sidecar": sidecar,
                "artifacts": artifacts[:10], "log_tail": lines[-5:]}
```

- [ ] **Step 4: Run unit tests, then the real-godot integration test**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/evals/test_godot_roundtrip.py -q`
Expected: all PASS including `test_real_godot_imports_a_real_fixture` (godot 4.6.3 is installed and fixtures exist locally). **If the integration test fails on a KNOWN-GOOD fixture because headless Godot prints a benign `ERROR:` line unrelated to the asset (e.g. editor-settings noise), tighten the filter to only count lines mentioning the asset/import (e.g. `"asset.glb" in line or "gltf" in line.lower()`), re-run, and note the exact benign line in the module docstring.** Do not weaken `returncode`/`sidecar`/`artifacts` checks.

- [ ] **Step 5: Full suite, commit**

```bash
git add src/niua_blender_mcp/evals/godot_roundtrip.py tests/evals/test_godot_roundtrip.py
git commit -m "feat: standalone headless-Godot round-trip import verifier (apex done-signal)"
```

---

### Task 7: Wire the Godot gate + finisher path into the benchmark runner and scoring

The runner exports each measured subject to .glb and round-trips it through Godot; the card and aggregate gain a `godot_import` axis (reported alongside readiness/preservation — NOT folded into the readiness fraction, so pre/post numbers stay comparable).

**Files:**
- Modify: `scripts/run_objective_benchmark.py`
- Modify: `src/niua_blender_mcp/evals/objective_bench.py`
- Test: `tests/evals/test_objective_bench.py` (extend), `tests/evals/test_objective_runner.py` (extend)

**Interfaces:**
- Consumes: Task 6's `verify_gltf_import`; existing `_safe`, `run_item`, `score_item_objective`, `aggregate_objective`; live tool `io.export` (params: `path`, `format`, `objects` comma-separated).
- Produces: `score_item_objective(..., godot_import: dict | None = None)` → card gains `godot_import_ok: bool | None`, `godot_import_measured: bool`; `aggregate_objective` gains `n_godot_measured`, `n_godot_import_ok`. Runner flags: `--godot-bin` (default `"godot"`), `--no-godot`.

- [ ] **Step 1: Write the failing scoring tests**

Add to `tests/evals/test_objective_bench.py`:

```python
def test_godot_axis_measured_ok():
    card = score_item_objective(
        {"id": "x", "asset_class": "organic_prop"},
        readiness=0.5, stage_pass_fraction=0.5,
        preservation=1.0, preservation_available=True,
        godot_import={"available": True, "ok": True},
    )
    assert card["godot_import_measured"] is True and card["godot_import_ok"] is True


def test_godot_axis_unmeasured_is_none_not_false():
    for gi in (None, {"available": False, "reason": "no binary"}):
        card = score_item_objective(
            {"id": "x", "asset_class": "organic_prop"},
            readiness=0.5, stage_pass_fraction=0.5,
            preservation=1.0, preservation_available=True, godot_import=gi,
        )
        assert card["godot_import_measured"] is False
        assert card["godot_import_ok"] is None


def test_aggregate_counts_godot_axis():
    ok = {"godot_import_measured": True, "godot_import_ok": True}
    bad = {"godot_import_measured": True, "godot_import_ok": False}
    unm = {"godot_import_measured": False, "godot_import_ok": None}
    base = {"asset_class": "a", "readiness_measured": True, "readiness": 1.0,
            "stage_pass_fraction": 1.0, "preservation_measured": True,
            "preservation": 1.0, "preservation_pass": True,
            "harm_flagged": False, "fully_ready": True}
    agg = aggregate_objective([{**base, **ok}, {**base, **bad}, {**base, **unm}])
    assert agg["n_godot_measured"] == 2
    assert agg["n_godot_import_ok"] == 1
```

(match the existing import style at the top of that test file.)

- [ ] **Step 2: Run to verify failure**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/evals/test_objective_bench.py -q`
Expected: the 3 new tests FAIL (unexpected keyword / missing keys).

- [ ] **Step 3: Extend `objective_bench.py`**

In `score_item_objective`, add the keyword-only param `godot_import: dict | None = None` and, before the return, compute and include:

```python
    godot_measured = bool(godot_import and godot_import.get("available"))
    # in the returned dict:
        "godot_import_ok": bool(godot_import.get("ok")) if godot_measured else None,
        "godot_import_measured": godot_measured,
```

In `aggregate_objective`'s returned dict add:

```python
        "n_godot_measured": sum(1 for c in cards if c.get("godot_import_measured")),
        "n_godot_import_ok": sum(1 for c in cards if c.get("godot_import_ok")),
```

Update the module docstring's UNMEASURED paragraph to mention the third axis ("godot_import follows the same rule: no binary / no export = unmeasured `None`, never a fake fail").

- [ ] **Step 4: Wire the runner**

In `scripts/run_objective_benchmark.py`:

1. Import: `from niua_blender_mcp.evals.godot_roundtrip import verify_gltf_import  # noqa: E402`
2. Add `"io.export"` to `_RUNNER_TOOLS`.
3. Add a helper:

```python
def _godot_roundtrip(bridge: BlenderBridge, subject: str, item: dict,
                     outdir: Path, godot_bin: str) -> dict:
    """Export the finished subject and round-trip it through headless Godot (the apex
    done-signal: ground truth, not a Blender-side proxy). Unmeasured on export failure."""
    path = outdir / "exports" / f"{item['id']}.glb"
    path.parent.mkdir(parents=True, exist_ok=True)
    exported = _safe(bridge, "io.export", {"path": str(path), "format": "GLB", "objects": subject})
    if exported is None:
        return {"available": False, "reason": "io.export failed"}
    return verify_gltf_import(str(path), godot_bin=godot_bin)
```

4. Change `run_item(bridge, item, finisher)` to `run_item(bridge, item, finisher, godot_fn=None)`; after the `pres` read add:

```python
    godot = godot_fn(bridge, subject, item) if godot_fn else None
```

and pass `godot_import=godot` into BOTH `score_item_objective` calls (the build-failed early return passes `godot_import=None`).

5. In `main()`: add `ap.add_argument("--godot-bin", default="godot")` and `ap.add_argument("--no-godot", action="store_true")`; build

```python
    outdir = Path(args.outdir)  # move this line up, before the run loop
    godot_fn = None if args.no_godot else (
        lambda bridge, subject, item: _godot_roundtrip(bridge, subject, item, outdir, args.godot_bin))
    cards = [run_item(bridge, it, finisher, godot_fn) for it in items]
```

and record `"godot_bin": None if args.no_godot else args.godot_bin` in `out["meta"]`.

6. Update the module docstring: scoring now includes the Godot round-trip axis in both modes (baseline round-trips the RAW intake — informative, still honest).

- [ ] **Step 5: Extend the runner tests**

Add to `tests/evals/test_objective_runner.py`:

```python
def test_runner_tools_include_export_for_godot_roundtrip():
    runner = _load_runner()
    assert "io.export" in runner._RUNNER_TOOLS
    assert runner._RUNNER_TOOLS <= runner.known_tools()


def test_finisher_entrypoint_resolves():
    runner = _load_runner()
    fn = runner._load_finisher("niua_blender_mcp.evals.finisher:finish")
    assert callable(fn)


def test_finisher_tools_are_known_to_the_runner_guard():
    from niua_blender_mcp.evals.finisher import TOOLS_USED
    runner = _load_runner()
    assert TOOLS_USED <= runner.known_tools(), sorted(TOOLS_USED - runner.known_tools())
```

- [ ] **Step 6: Full suite, commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS.

```bash
git add scripts/run_objective_benchmark.py src/niua_blender_mcp/evals/objective_bench.py \
        tests/evals/test_objective_bench.py tests/evals/test_objective_runner.py
git commit -m "feat: Godot round-trip import axis in the objective benchmark (export -> headless godot --import)"
```

---

### Task 8: M0 context prose (Phase 5) + ledger

The deleted knowledge/recipes/guidance return as prompt prose — higher-resolution, trivially editable. Update the `refine_mesh` prompt with the finisher charter, intake triage, the standard finishing order, and the apex done-signal.

**Files:**
- Modify: `src/niua_blender_mcp/prompts.py`
- Modify: `.superpowers/sdd/lean-rebuild.md`
- Test: `tests/test_server.py` / existing prompt tests keep passing (prompts are rendered strings; no schema change)

**Interfaces:**
- Consumes: nothing new. Produces: prose only.

- [ ] **Step 1: Edit `_refine_mesh` in `prompts.py`**

Insert AFTER the "THE CORE LOOP" paragraph (prompts.py:100-104) and BEFORE step "6. REPEAT":

```
   INTAKE TRIAGE (once, before any edit): decide what you are holding from the multi-angle
   captures, and set `asset_class` yourself on every `feedback.readiness` / `feedback.quality`
   call — organic_prop for sculpt/creature forms, hard_surface_prop for machined/panel forms,
   generated_cleanup for noisy generated or scanned meshes. Never let the class default silently:
   a wrong class is a wrong numeric contract. If the input has no readable form at all (a blob,
   noise, an empty hull), DECLINE it: you are a technical finisher — report that the input needs
   regeneration rather than smoothing noise into a smooth nothing.

   THE STANDARD FINISHING ORDER (guidance, not a gate — the readiness gates are order-free):
   repair (doubles / normals / non-manifold) -> density to budget (decimate or retopo) ->
   tris-to-quads -> UV unwrap + pack -> materials / PBR maps -> LODs -> collision ->
   apply transforms -> export. Deviate when the mesh tells you to; re-measure after every step.

   THE APEX DONE-SIGNAL: readiness == 1.0 in Blender is still a proxy. Ground truth is a clean
   engine import of the exported .glb (no errors, sidecar + import artifacts produced). When a
   `godot` binary is available, round-trip the export headlessly before declaring done.
```

Keep indentation consistent with the surrounding numbered list (three-space hang like the CORE LOOP paragraph).

- [ ] **Step 2: Update the ledger**

Append to `.superpowers/sdd/lean-rebuild.md`:

```
- [x] Phase 3: FSM control surface DELETED (gates extracted to core/gates.py; feedback.readiness untouched)
- [x] Phase 4: scaffolding DELETED (craft_workflow, knowledge, modeling_verbs, playbooks, asset-class prose; profiles = base + deltas)
- [x] Phase 5: Godot round-trip axis in the bench (evals/godot_roundtrip.py, standalone headless godot); M0 prose (triage + finishing order + apex) in prompts.py
- [x] FINISHER: deterministic gate-driven reference finisher (evals/finisher.py) wired via --mode agent
```

- [ ] **Step 3: Full suite, commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`

```bash
git add src/niua_blender_mcp/prompts.py .superpowers/sdd/lean-rebuild.md
git commit -m "docs: M0 context prose — intake triage, finishing order, apex done-signal (Phase 5)"
```

---

### Task 9: Live verification — bench unchanged after deletions, then the first real finishing run

This task runs against a live visible Blender. It validates the subtractive phases ("objective bench unchanged") and then produces the first honest agent-mode reading.

**Files:**
- Create: `docs/reports/agent-finisher-first-run.md`
- Modify: `docs/reports/objective-baseline.md` (append post-deletion confirmation)

- [ ] **Step 1: Launch Blender with the bridge**

```bash
pkill -f blender_gui.py || true
```

Then (separate command, background): `blender --python scripts/blender_gui.py -- /home/frankyin/Desktop/lab/lab-niua-blender/blender_addon 8765`
Wait for the port: `python -c "import socket,time
for _ in range(60):
    try: socket.create_connection(('127.0.0.1',8765),1).close(); break
    except OSError: time.sleep(1)"`

- [ ] **Step 2: Baseline mode — confirm the deletions changed nothing**

Run: `python scripts/run_objective_benchmark.py --no-godot --outdir /tmp/niua_objective_post_delete`
Expected: 5/5 measured; readiness real_character 0.36, real_character_light 0.36, real_creature 0.36, real_multipart 0.24, real_prop 0.28 (±0.00 — the bench is deterministic); preservation 1.0 on all. **Any drift = a deletion broke something: STOP, bisect the phase commits, fix before proceeding.**

- [ ] **Step 3: Baseline mode WITH the Godot axis**

Run: `python scripts/run_objective_benchmark.py --outdir /tmp/niua_objective_baseline_godot`
Expected: `n_godot_measured == 5`; record how many raw intakes already import clean (informative baseline for the new axis).

- [ ] **Step 4: Agent mode — the first real finishing run**

Run: `python scripts/run_objective_benchmark.py --mode agent --finisher niua_blender_mcp.evals.finisher:finish --outdir /tmp/niua_objective_agent`
Expected: it completes on all 5 items (per-move stderr log shows KEPT/REVERTED decisions). Success criteria for the reading itself: `mean_readiness` strictly above the 0.24–0.36 baseline band, `n_harm_flagged == 0`, and no item regresses below its baseline readiness (the accept/revert loop makes regression structurally impossible unless a bug exists — treat any regression as a bug to investigate, not a result to report). Timeboxing: the 978k-tri `real_prop` decimate may take minutes; the runner's 120s per-call timeout marks a too-slow call unmeasured rather than hanging — report honestly whatever happens.

- [ ] **Step 5: Write the report**

Create `docs/reports/agent-finisher-first-run.md` recording: the post-deletion baseline confirmation, the Godot-axis baseline, the agent-mode per-item table (readiness before → after, preservation, godot_import_ok, moves kept/reverted per item), and a "next gaps" section listing every move that errored/reverted and every gate group still failing after the run (this list IS the next roadmap). Append a one-line post-deletion confirmation to `docs/reports/objective-baseline.md`.

- [ ] **Step 6: Commit**

```bash
git add docs/reports/agent-finisher-first-run.md docs/reports/objective-baseline.md
git commit -m "docs: first real finisher run — post-deletion bench unchanged; agent-mode + godot-axis readings"
```

---

## Self-Review

1. **Spec coverage:** finisher (Tasks 5, 7, 9) ✓; Phase 3 strangle-FSM (Tasks 1, 2, 4) ✓; Phase 4 scaffolding + prose (Tasks 3, 4) ✓; Phase 5 Godot gate + intake triage + M0 prose (Tasks 6, 7, 8 — triage delivered as prose per audit "thin/prose", not a new tool; a triage TOOL is intentionally out of scope until an agent measurably fails without it, per "no structure without a measured caller") ✓; "bench unchanged" validation (Task 9 Step 2) ✓.
2. **Placeholder scan:** the `_GATES` paste marker in Task 1 references exact source lines to copy verbatim (a move, not new content); Task 5's param-name verification note is a deliberate cross-check instruction, not deferred design. No TBDs.
3. **Type consistency:** `stage_gates` tuple return shape preserved through Task 1 (feedback.py destructures `gates, _applied`); `finish(bridge, subject, item)` matches the runner's `finisher(bridge, subject, item)` call at run_item; `run_item` gains optional 4th arg with default so `test_objective_runner.py` existing calls survive; card/aggregate key names consistent between Task 7 scoring code and its tests.
