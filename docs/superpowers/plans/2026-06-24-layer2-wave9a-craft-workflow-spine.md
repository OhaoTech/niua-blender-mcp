# Layer 2 Wave 9A Craft Workflow Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mirrored craft workflow registry and one real hard-surface workflow vertical slice so Layer 2 can recommend and run a deterministic craft move from asset class plus pipeline stage.

**Architecture:** Add server/add-on workflow registries with read-only workflow tools, then add `hard_surface.panel_detail_pass` as a curated mutating craft verb. Recommendation stays deterministic and narrow; no generic recipe executor is introduced in this wave.

**Tech Stack:** Python 3, pytest, existing niua MCP `ToolSpec` manifests, add-on `Command` registry, fake-bpy unit tests, Blender headless smoke tests, HTML architecture doc.

## Global Constraints

- Use mirrored registries, not a single imported file, because server and add-on run in different Python contexts.
- Initial workflow id is exactly `hard_surface.panel_detail_pass`.
- Initial workflow asset class is exactly `hard_surface_prop`.
- Initial workflow stages are exactly `repair` and `retopo`.
- `craft_workflow.recommend` returns an empty list for unsupported asset classes; it must not invent a fallback workflow.
- `hard_surface.panel_detail_pass` is curated, `mutates=True`, `feedback="viewport"`, and `tier="curated"` on the server spec.
- The composite verb must run inside `ctx.ensure(active=obj, mode="EDIT", select=[obj])`.
- No generic workflow executor, no all-class workflow breadth, and no new pipeline stage in Wave 9A.
- Preserve existing user changes, including unrelated `.gitignore` worktree changes.

---

## File Map

- Create `blender_addon/niua_mcp_bridge/core/craft_workflows.py`: add-on workflow data, lookup, filtering, and recommendation helpers.
- Create `src/niua_blender_mcp/craft_workflows.py`: mirrored server workflow data for parity and enum choices.
- Create `blender_addon/niua_mcp_bridge/domains/craft_workflow.py`: add-on handlers for `craft_workflow.list`, `craft_workflow.describe`, and `craft_workflow.recommend`.
- Create `src/niua_blender_mcp/domains/craft_workflow.py`: server `ToolSpec`s for workflow tools.
- Modify `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`: add `panel_detail_pass`.
- Modify `src/niua_blender_mcp/domains/modeling_verbs.py`: add `hard_surface.panel_detail_pass` spec.
- Modify `tests/test_craft_workflows.py`: registry parity and helper tests.
- Create `tests/domains/test_craft_workflow.py`: command registration and handler tests.
- Modify `tests/domains/test_modeling_verbs.py`: fake-bpy sequence test for the composite verb.
- Modify `tests/test_smoke_headless.py`: Wave 9A headless acceptance.
- Modify `docs/layer2-architecture.html`: mark Wave 9A workflow spine as current/built and show the next workflow breadth waves.

---

### Task 1: Mirrored Craft Workflow Registries

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/craft_workflows.py`
- Create: `src/niua_blender_mcp/craft_workflows.py`
- Test: `tests/test_craft_workflows.py`

**Interfaces:**
- Produces: `WORKFLOW_IDS: list[str]`
- Produces: `list_workflows(asset_class: str | None = None, stage: str | None = None) -> list[dict[str, Any]]`
- Produces: `get_workflow(workflow_id: str) -> dict[str, Any]`
- Produces: `recommend_workflows(asset_class: str | None = None, stage: str | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write failing registry tests**

Add tests that import both modules, assert identical workflow records, assert the first id is `hard_surface.panel_detail_pass`, assert returned records are deep copies, assert retopo recommendation returns the hard-surface workflow, and assert organic recommendation returns an empty recommendation list.

- [ ] **Step 2: Run red test**

Run: `pytest tests/test_craft_workflows.py -q`

Expected: fail because `craft_workflows` modules do not exist.

- [ ] **Step 3: Implement mirrored registries**

Create the two registry modules with identical `_WORKFLOWS` data from the design spec and helper functions. `recommend_workflows` must resolve explicit `asset_class` and `stage` before state values, return `{"recommendations": [...], "reason": "..."}`, and only include workflows whose asset class matches.

- [ ] **Step 4: Run green test**

Run: `pytest tests/test_craft_workflows.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_craft_workflows.py src/niua_blender_mcp/craft_workflows.py blender_addon/niua_mcp_bridge/core/craft_workflows.py
git commit -m "feat: add craft workflow registry"
```

### Task 2: Workflow Tool Surface

**Files:**
- Create: `blender_addon/niua_mcp_bridge/domains/craft_workflow.py`
- Create: `src/niua_blender_mcp/domains/craft_workflow.py`
- Test: `tests/domains/test_craft_workflow.py`

**Interfaces:**
- Consumes: registry functions from Task 1.
- Produces commands/specs: `craft_workflow.list`, `craft_workflow.describe`, `craft_workflow.recommend`.

- [ ] **Step 1: Write failing domain tests**

Test that `build_router().specs()` and `build_default_registry()` both expose the three workflow tools. Test list filtering, describe, unknown workflow error, hard-surface recommendation, and unsupported organic recommendation.

- [ ] **Step 2: Run red test**

Run: `pytest tests/domains/test_craft_workflow.py -q`

Expected: fail because workflow domain modules do not exist.

- [ ] **Step 3: Implement server and add-on domains**

Server specs use `Enum(ASSET_CLASS_IDS)` for optional asset class, `Enum(WORKFLOW_IDS)` for required describe workflow, and `Str` for optional stage/object. Add-on handlers validate required describe workflow and wrap unknown ids as `invalid_params`.

- [ ] **Step 4: Run green test**

Run: `pytest tests/domains/test_craft_workflow.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/domains/test_craft_workflow.py src/niua_blender_mcp/domains/craft_workflow.py blender_addon/niua_mcp_bridge/domains/craft_workflow.py
git commit -m "feat: expose craft workflow tools"
```

### Task 3: Hard-Surface Composite Craft Verb

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`
- Modify: `src/niua_blender_mcp/domains/modeling_verbs.py`
- Modify: `tests/domains/test_modeling_verbs.py`

**Interfaces:**
- Produces command/spec: `hard_surface.panel_detail_pass`.

- [ ] **Step 1: Write failing fake-bpy test**

Add a test that calls `modeling_verbs.panel_detail_pass(Ctx(bpy), {"object": "Cube"})`, asserts the ordered operator calls are:

```python
[
    ("mesh.select_all", {"action": "SELECT"}),
    ("mesh.inset", {"thickness": 0.08, "depth": -0.04, "use_individual": True}),
    ("mesh.select_all", {"action": "DESELECT"}),
    ("mesh.edges_select_sharp", {"sharpness": math.radians(30.0)}),
    ("mesh.bevel", {"offset": 0.02, "segments": 2, "affect": "EDGES"}),
    ("mesh.select_all", {"action": "SELECT"}),
    ("mesh.tris_convert_to_quads", {"face_threshold": math.radians(40.0), "shape_threshold": math.radians(40.0)}),
    ("mesh.normals_make_consistent", {}),
    ("mesh.remove_doubles", {}),
]
```

Assert returned `workflow_id`, `asset_class`, `applied`, default `params`, and warning string.

- [ ] **Step 2: Run red test**

Run: `pytest tests/domains/test_modeling_verbs.py::test_panel_detail_pass_runs_hard_surface_sequence -q`

Expected: fail because `panel_detail_pass` does not exist.

- [ ] **Step 3: Implement handler and spec**

Implement the handler in one `ctx.ensure(active=obj, mode="EDIT", select=[obj])` block. Use the same mesh validation style as existing model verbs. Add a server `ToolSpec` with category `modeling`, name/command `hard_surface.panel_detail_pass`, mutates true, viewport feedback, tier curated, and params from the design.

- [ ] **Step 4: Run green tests**

Run:

```bash
pytest tests/domains/test_modeling_verbs.py -q
python -c "from niua_blender_mcp.domains import build_router; print('hard_surface.panel_detail_pass' in {s.name for s in build_router().specs()})"
```

Expected: pytest pass and Python prints `True`.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/domains/test_modeling_verbs.py src/niua_blender_mcp/domains/modeling_verbs.py blender_addon/niua_mcp_bridge/domains/modeling_verbs.py
git commit -m "feat: add hard-surface panel detail pass"
```

### Task 4: Wave 9A Acceptance and Architecture Doc

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/layer2-architecture.html`

**Interfaces:**
- Consumes: Tasks 1-3 command names and outputs.

- [ ] **Step 1: Write failing acceptance test**

Add a headless smoke test that creates a cube, starts a pipeline with `asset_class="hard_surface_prop"`, advances to retopo, calls `craft_workflow.recommend`, calls `hard_surface.panel_detail_pass`, and then calls `feedback.quality` plus `pipeline.gate_check`.

- [ ] **Step 2: Run targeted red/green acceptance**

Run:

```bash
pytest tests/test_smoke_headless.py::test_layer2_wave9a_craft_workflow_acceptance -q
```

Expected before implementation: fail if Task 3 is absent; after Tasks 1-3: pass when Blender is available, otherwise skip under existing smoke-test rules.

- [ ] **Step 3: Update architecture diagram**

Update `docs/layer2-architecture.html` so the current map shows `asset class -> craft workflow recommend -> hard_surface.panel_detail_pass -> gates`, and the roadmap shows Wave 9B+ workflow breadth.

- [ ] **Step 4: Final verification**

Run:

```bash
pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py tests/domains/test_modeling_verbs.py -q
pytest -q
python tools/audit_layer1_gui_parity.py --fail-on partial
python - <<'PY'
from html.parser import HTMLParser
from pathlib import Path

class Parser(HTMLParser):
    pass

Parser().feed(Path("docs/layer2-architecture.html").read_text())
print("html_parse_ok")
PY
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "docs: update layer 2 workflow map"
```

## Self-Review Checklist

- Registry parity covers server and add-on records.
- Router/add-on command parity covers all new workflow tools and the composite verb.
- Recommendation has a no-fallback test for unsupported asset classes.
- Composite verb has an operator-sequence fake-bpy test.
- Headless acceptance proves workflow recommendation, command invocation, and post-command gates in one path.
- Diagram reflects the current big map and does not describe unsupported all-class workflow breadth as built.
