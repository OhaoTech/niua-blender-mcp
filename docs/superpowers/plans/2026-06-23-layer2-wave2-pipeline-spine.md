# Layer 2 Wave 2 Pipeline Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Layer 2 gated pipeline state machine: start/status/gate_check/advance/rollback, plus one live end-to-end path through repair, retopo, UV, export preflight, and GLB export.

**Architecture:** Pipeline state lives in the Blender add-on session, next to session checkpoints, because it tracks a live object and must survive across MCP calls. Server-side `pipeline.*` specs mirror add-on commands. Deterministic gates reuse the Wave 1 metrics and gate profiles; visual/perception tools remain separate and are not duplicated in the pipeline domain.

**Tech Stack:** Python 3.11+, stdlib only, existing auto-discovered domain pattern, pytest fake-bpy tests, real headless Blender smoke tests.

## Global Constraints

- Do not implement bake/material/LOD automation in Wave 2; keep those as future registry stages.
- Pipeline tools may mutate pipeline/session stores, but only `pipeline.rollback` mutates the visible Blender scene.
- Every `pipeline.advance` must gate-check the current stage before moving forward.
- `pipeline.rollback` restores from the target stage entry checkpoint and moves the current stage pointer back to that stage.
- Every task updates `docs/layer2-architecture.html`.
- Server/add-on parity must remain green.

---

## File Map

- `blender_addon/niua_mcp_bridge/core/pipeline.py` — add-on pipeline registry, state store, gate profiles, pure transition helpers.
- `blender_addon/niua_mcp_bridge/domains/pipeline.py` — add-on MCP handlers for `pipeline.start/status/gate_check/advance/rollback`.
- `src/niua_blender_mcp/domains/pipeline.py` — server `ToolSpec` definitions.
- `tests/core/test_pipeline_core.py` — pure pipeline state-machine tests.
- `tests/domains/test_pipeline.py` — fake-bpy command tests.
- `tests/test_smoke_headless.py` — live end-to-end pipeline acceptance.
- `docs/layer2-architecture.html` — visual map updated after each task.

---

### Task 1: UV overlap detection for gate readiness

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/uv_metrics.py`
- Test: `tests/core/test_uv_metrics.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces: `polygons_overlap_2d(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool`.
- Updates `uv_quality(...)"overlap_detected"` from `None` to a deterministic bool when UV loop polygons are available.

- [ ] Write failing tests for separated, touching, and overlapping UV polygons.
- [ ] Implement segment-intersection and point-in-polygon overlap helpers.
- [ ] Set `overlap_detected` in `uv_quality` by pairwise checking face UV polygons.
- [ ] Run `pytest tests/core/test_uv_metrics.py tests/evals/test_stage_gates.py -v`.
- [ ] Update `docs/layer2-architecture.html` to show UV overlap as gate-ready.
- [ ] Commit: `feat: add deterministic UV overlap metric`.

---

### Task 2: Pure pipeline registry and state store

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/pipeline.py`
- Test: `tests/core/test_pipeline_core.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- Produces:
  - `stage_registry() -> list[dict]`
  - `start(object_name: str, profile: str = "game_asset") -> dict`
  - `get_state(object_name: str) -> dict | None`
  - `status(object_name: str | None = None) -> dict`
  - `record_gate(object_name: str, stage: str, gate: dict) -> dict`
  - `advance(object_name: str) -> dict`
  - `rollback_pointer(object_name: str, stage: str) -> dict`
  - `reset() -> None`
- Stage order:
  `intake -> repair -> retopo -> uv -> material -> export_preflight -> exported`
- Gate profiles:
  - `intake`: no hard gates.
  - `repair`: `orientation`
  - `retopo`: `retopo`
  - `uv`: `uv`
  - `material`: no hard gates in Wave 2.
  - `export_preflight`: `export_preflight`
  - `exported`: terminal.

- [ ] Write failing tests that start a run, inspect registry/status, block advance on failing gates, advance on passing gates, and rollback pointer to an earlier stage.
- [ ] Implement the pure state store with deterministic statuses: `pending`, `current`, `passed`, `failed`, `complete`.
- [ ] Run `pytest tests/core/test_pipeline_core.py -v`.
- [ ] Update `docs/layer2-architecture.html` to mark pipeline registry/state as built.
- [ ] Commit: `feat: add pipeline registry and state store`.

---

### Task 3: pipeline.start/status/gate_check command surface

**Files:**
- Create: `blender_addon/niua_mcp_bridge/domains/pipeline.py`
- Create: `src/niua_blender_mcp/domains/pipeline.py`
- Test: `tests/domains/test_pipeline.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- MCP tools:
  - `pipeline.start(object, profile="game_asset")`
  - `pipeline.status(object?)`
  - `pipeline.gate_check(object, stage?)`
- `pipeline.gate_check` resolves the object, calls `feedback.quality`, checks the stage gate profile, records the result in pipeline state, and returns `{object, stage, metrics, gates, gates_pass, state}`.

- [ ] Write failing fake-bpy tests for server/add-on registration and status/start behavior.
- [ ] Implement add-on handlers. `pipeline.start` creates a `pipeline:intake:entry` checkpoint using the existing session store.
- [ ] Implement server specs.
- [ ] Run `pytest tests/domains/test_pipeline.py tests/test_parity.py -v`.
- [ ] Update `docs/layer2-architecture.html` to mark `pipeline.start/status/gate_check` built.
- [ ] Commit: `feat: add pipeline start/status/gate-check tools`.

---

### Task 4: pipeline.advance and pipeline.rollback

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/pipeline.py`
- Modify: `src/niua_blender_mcp/domains/pipeline.py`
- Test: `tests/domains/test_pipeline.py`
- Update: `docs/layer2-architecture.html`

**Interfaces:**
- MCP tools:
  - `pipeline.advance(object)` — gate-checks current stage and advances only on pass; creates the next stage entry checkpoint.
  - `pipeline.rollback(object, stage?)` — restores `pipeline:<stage>:entry` checkpoint and sets current stage to `stage`.

- [ ] Write failing fake-bpy tests: advance blocked by failing gate; advance creates next checkpoint on pass; rollback restores a checkpoint and pushes one undo step.
- [ ] Implement the handlers and server specs.
- [ ] Run `pytest tests/domains/test_pipeline.py tests/test_parity.py -v`.
- [ ] Update `docs/layer2-architecture.html` to mark `pipeline.advance/rollback` built.
- [ ] Commit: `feat: add gated pipeline advance and rollback`.

---

### Task 5: Live pipeline acceptance

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/layer2-architecture.html`

**Flow:**
1. Create cube `PipeHero`.
2. `pipeline.start`.
3. `pipeline.gate_check` and `pipeline.advance` through `intake`, `repair`, `retopo`.
4. Confirm UV gate fails before unwrap.
5. Run `uv.smart_unwrap` and `uv.pack_islands`.
6. Advance through `uv`, `material`, and `export_preflight`.
7. Export a real `.glb` with `io.export`.
8. Confirm pipeline status is at `exported` or complete.

- [ ] Add the live acceptance test.
- [ ] Run `pytest tests/test_smoke_headless.py::test_layer2_wave2_pipeline_spine_acceptance -v`.
- [ ] Run `pytest -q`.
- [ ] Run `python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on partial`.
- [ ] Update `docs/layer2-architecture.html` to mark Wave 2 built and Wave 3 next.
- [ ] Commit: `test: add Layer 2 Wave 2 pipeline acceptance`.

---

## Final Verification

- [ ] `pytest -q`
- [ ] `pytest tests/test_smoke_headless.py -v`
- [ ] `python scripts/audit_blender_coverage.py --source /home/frankyin/Desktop/lab/blender-source --fail-on partial`
- [ ] Router check: `pipeline.start`, `pipeline.status`, `pipeline.gate_check`, `pipeline.advance`, `pipeline.rollback` all exposed.
- [ ] Open `docs/layer2-architecture.html` and confirm Wave 2 is marked built and Wave 3 is marked next.

## Self-Review

- Wave 2 scope is the pipeline spine and one honest end-to-end path.
- Bake, material authoring, LOD, collision, and knowledge RAG remain Wave 3/4 work.
- The plan avoids fake pass conditions by adding deterministic UV overlap before using UV gates for advancement.
