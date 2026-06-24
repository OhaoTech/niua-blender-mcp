# Layer 2 Wave 9B Workflow Breadth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Layer 2 craft workflows beyond hard-surface props by adding generated-cleanup and organic retopo-prep workflows, real composite verbs, stable recommendation ranks, and acceptance coverage.

**Architecture:** Extend the existing mirrored `craft_workflows` registries on the server and Blender add-on sides. Keep workflow discovery through `craft_workflow.*`; add two explicit curated Python handlers in `modeling_verbs.py` rather than a generic recipe executor.

**Tech Stack:** Python 3, pytest, existing niua MCP `ToolSpec` manifests, add-on `Command` registry, fake-bpy unit tests, Blender headless smoke tests, HTML architecture doc, gstack browser for diagram screenshot checks.

## Global Constraints

- No generic workflow executor.
- No dynamic recipe runner.
- No UV, bake, or material workflow breadth in this wave.
- No new pipeline stages.
- No sculpt brush automation.
- No destructive simplification that claims to preserve final quality without gates.
- New workflow ids are exactly `generated_cleanup.rebuild_noisy_mesh` and `organic.silhouette_retopo_prep`.
- New command names are exactly `model.generated_cleanup_pass` and `model.organic_retopo_prep`.
- Every recommendation record includes stable `rank`, starting at `1`.
- Optional Blender operator skips must be returned in `skipped`, not hidden.
- `model.organic_retopo_prep` must not call bevel, panel inset, or loose-fragment deletion by default.
- Preserve unrelated worktree changes, including the existing unstaged `.gitignore` change.

---

## File Map

- Modify `src/niua_blender_mcp/craft_workflows.py`: add two workflow records and stable ranking in `recommend_workflows`.
- Modify `blender_addon/niua_mcp_bridge/core/craft_workflows.py`: mirror the server workflow records and ranking behavior.
- Modify `tests/test_craft_workflows.py`: registry parity, workflow id list, generated/organic recommendations, rank, and no fallback for `from_scratch_prop`.
- Modify `tests/domains/test_craft_workflow.py`: workflow tool integration for new records and rank through the add-on command surface.
- Modify `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`: add tiny validation/default helpers, `generated_cleanup_pass`, and `organic_retopo_prep`.
- Modify `src/niua_blender_mcp/domains/modeling_verbs.py`: add server specs for the two new curated verbs.
- Modify `tests/domains/test_modeling_verbs.py`: fake-bpy tests for generated cleanup available/unavailable `delete_loose`, organic prep sequence, and router exposure.
- Modify `tests/test_smoke_headless.py`: Wave 9B headless acceptance for generated and organic workflow paths.
- Modify `docs/layer2-architecture.html`: mark Wave 9B as current and move next wave to UV/bake/material workflow breadth.

---

### Task 1: Workflow Registry Breadth and Stable Rank

**Files:**
- Modify: `src/niua_blender_mcp/craft_workflows.py`
- Modify: `blender_addon/niua_mcp_bridge/core/craft_workflows.py`
- Modify: `tests/test_craft_workflows.py`
- Modify: `tests/domains/test_craft_workflow.py`

**Interfaces:**
- Consumes: existing `list_workflows`, `get_workflow`, and `recommend_workflows` APIs.
- Produces: `WORKFLOW_IDS == ["generated_cleanup.rebuild_noisy_mesh", "hard_surface.panel_detail_pass", "organic.silhouette_retopo_prep"]`.
- Produces: recommendation records with `rank: int`.

- [ ] **Step 1: Write failing registry tests**

Update `tests/test_craft_workflows.py` so the id assertion becomes:

```python
assert sorted(server) == [
    "generated_cleanup.rebuild_noisy_mesh",
    "hard_surface.panel_detail_pass",
    "organic.silhouette_retopo_prep",
]
```

Update `test_list_workflows_filters_by_asset_class_and_stage`:

```python
generated = addon_workflows.list_workflows(asset_class="generated_cleanup", stage="retopo")
organic = addon_workflows.list_workflows(asset_class="organic_prop", stage="retopo")
scratch = addon_workflows.list_workflows(asset_class="from_scratch_prop", stage="retopo")

assert [workflow["id"] for workflow in generated] == ["generated_cleanup.rebuild_noisy_mesh"]
assert [workflow["id"] for workflow in organic] == ["organic.silhouette_retopo_prep"]
assert scratch == []
```

Add:

```python
def test_recommend_workflows_returns_generated_cleanup_match_with_rank() -> None:
    out = addon_workflows.recommend_workflows(asset_class="generated_cleanup", stage="retopo")

    assert out["reason"] == "matched asset_class=generated_cleanup stage=retopo"
    assert out["recommendations"][0]["id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert out["recommendations"][0]["rank"] == 1
    assert out["recommendations"][0]["match"] == "asset_class+stage"


def test_recommend_workflows_returns_organic_match_with_rank() -> None:
    out = addon_workflows.recommend_workflows(asset_class="organic_prop", stage="retopo")

    assert out["reason"] == "matched asset_class=organic_prop stage=retopo"
    assert out["recommendations"][0]["id"] == "organic.silhouette_retopo_prep"
    assert out["recommendations"][0]["rank"] == 1
    assert out["recommendations"][0]["match"] == "asset_class+stage"


def test_recommend_workflows_returns_no_fallback_for_from_scratch_class() -> None:
    out = addon_workflows.recommend_workflows(asset_class="from_scratch_prop", stage="retopo")

    assert out == {
        "recommendations": [],
        "reason": "no workflow matched asset_class=from_scratch_prop stage=retopo",
    }
```

Update existing recommendation tests to assert hard-surface rank:

```python
assert out["recommendations"][0]["rank"] == 1
```

- [ ] **Step 2: Write failing domain tests**

Update `tests/domains/test_craft_workflow.py`:

```python
def test_craft_workflow_list_includes_wave9b_workflows() -> None:
    generated = _dispatch("craft_workflow.list", {"asset_class": "generated_cleanup", "stage": "retopo"})
    organic = _dispatch("craft_workflow.list", {"asset_class": "organic_prop", "stage": "retopo"})

    assert [workflow["id"] for workflow in generated["workflows"]] == ["generated_cleanup.rebuild_noisy_mesh"]
    assert [workflow["id"] for workflow in organic["workflows"]] == ["organic.silhouette_retopo_prep"]


def test_craft_workflow_recommend_returns_wave9b_ranks() -> None:
    generated = _dispatch("craft_workflow.recommend", {"asset_class": "generated_cleanup", "stage": "retopo"})
    organic = _dispatch("craft_workflow.recommend", {"asset_class": "organic_prop", "stage": "retopo"})

    assert generated["recommendations"][0]["id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert generated["recommendations"][0]["rank"] == 1
    assert organic["recommendations"][0]["id"] == "organic.silhouette_retopo_prep"
    assert organic["recommendations"][0]["rank"] == 1
```

Update the unsupported-class domain test to use `from_scratch_prop`, because organic is now supported:

```python
out = _dispatch("craft_workflow.recommend", {"asset_class": "from_scratch_prop", "stage": "retopo"})
assert out == {
    "recommendations": [],
    "reason": "no workflow matched asset_class=from_scratch_prop stage=retopo",
}
```

- [ ] **Step 3: Run red tests**

Run:

```bash
pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py -q
```

Expected: fail because the new workflow ids do not exist and recommendation records do not include `rank`.

- [ ] **Step 4: Implement registry records and rank**

Add these two records to both `src/niua_blender_mcp/craft_workflows.py` and `blender_addon/niua_mcp_bridge/core/craft_workflows.py`:

```python
"generated_cleanup.rebuild_noisy_mesh": {
    "id": "generated_cleanup.rebuild_noisy_mesh",
    "label": "Generated cleanup rebuild noisy mesh",
    "asset_class": "generated_cleanup",
    "stages": ["repair", "retopo"],
    "summary": "Remove common generated-mesh noise, normalize normals, merge duplicates, and rebuild compatible quads.",
    "required_tools": ["model.generated_cleanup_pass", "model.retopo_quads", "feedback.topology"],
    "default_params": {"face_threshold": 35.0, "merge_distance": 0.0005},
    "gate_targets": ["topology.ngons", "topology.quad_ratio", "topology.non_manifold_edges"],
    "recipe_steps": [
        "select all mesh elements",
        "make normals consistent",
        "merge duplicate or near-duplicate vertices",
        "delete loose generated fragments when Blender exposes the operator",
        "convert compatible triangles back to quads",
        "re-check strict generated-cleanup topology gates",
    ],
    "outputs": ["normalized normals", "merged duplicate vertices", "quad-normalized generated mesh"],
    "cautions": [
        "Generated cleanup can erase intentional tiny detail; checkpoint before running.",
        "A pass that makes topology cleaner can still damage silhouette; inspect after gates.",
    ],
},
"organic.silhouette_retopo_prep": {
    "id": "organic.silhouette_retopo_prep",
    "label": "Organic silhouette retopo prep",
    "asset_class": "organic_prop",
    "stages": ["repair", "retopo"],
    "summary": "Normalize organic topology without hard-surface bevel or panel operations.",
    "required_tools": ["model.organic_retopo_prep", "model.retopo_quads", "feedback.topology"],
    "default_params": {"face_threshold": 50.0, "merge_distance": 0.0002},
    "gate_targets": ["topology.ngons", "topology.quad_ratio", "topology.non_manifold_edges"],
    "recipe_steps": [
        "select all mesh elements",
        "make normals consistent",
        "lightly merge duplicate vertices",
        "convert compatible triangles to quads with a relaxed threshold",
        "leave silhouette decisions to gates and visual review",
    ],
    "outputs": ["consistent normals", "light duplicate cleanup", "organic retopo-prep topology"],
    "cautions": [
        "Do not bevel organic contours as a default cleanup move.",
        "Keep poles and triangles away from visible silhouette and deformation-like flow regions.",
    ],
},
```

Change `_recommendation` to accept rank:

```python
def _recommendation(workflow: dict[str, Any], match: str, rank: int) -> dict[str, Any]:
    return {
        "id": workflow["id"],
        "rank": rank,
        "label": workflow["label"],
        "asset_class": workflow["asset_class"],
        "stages": deepcopy(workflow["stages"]),
        "summary": workflow["summary"],
        "required_tools": deepcopy(workflow["required_tools"]),
        "match": match,
    }
```

When building matches, enumerate sorted registry-order matches:

```python
matches = [
    _recommendation(workflow, "asset_class+stage", index)
    for index, workflow in enumerate(list_workflows(resolved_asset_class, resolved_stage), start=1)
]
```

Do the same for asset-class-only matches.

- [ ] **Step 5: Run green tests**

Run:

```bash
pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add tests/test_craft_workflows.py tests/domains/test_craft_workflow.py src/niua_blender_mcp/craft_workflows.py blender_addon/niua_mcp_bridge/core/craft_workflows.py
git commit -m "feat: add workflow breadth registry"
```

### Task 2: Generated Cleanup Composite Verb

**Files:**
- Modify: `tests/domains/test_modeling_verbs.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`
- Modify: `src/niua_blender_mcp/domains/modeling_verbs.py`

**Interfaces:**
- Consumes: `generated_cleanup.rebuild_noisy_mesh` workflow defaults from Task 1.
- Produces: add-on handler `generated_cleanup_pass(ctx, payload) -> dict`.
- Produces: server spec `model.generated_cleanup_pass`.

- [ ] **Step 1: Extend fake-bpy with `delete_loose`**

In `tests/domains/test_modeling_verbs.py`, add to `_MeshOps`:

```python
delete_loose = _Op(log, "mesh.delete_loose")
```

- [ ] **Step 2: Write failing generated-cleanup available-path test**

Add:

```python
def test_generated_cleanup_pass_runs_available_delete_loose_sequence(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "model.generated_cleanup_pass", {"object": "Cube"}, Ctx(bpy))

    assert out["object"] == "Cube"
    assert out["asset_class"] == "generated_cleanup"
    assert out["workflow_id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert out["applied"] == [
        "select_all",
        "normals_make_consistent",
        "remove_doubles",
        "delete_loose",
        "tris_convert_to_quads",
    ]
    assert out["skipped"] == []
    assert out["params"] == {"face_threshold": 35.0, "merge_distance": 0.0005}
    assert out["postcheck_recommended"] == ["feedback.topology", "pipeline.gate_check"]
    assert out["warnings"] == [
        "Generated cleanup can erase intentional tiny detail; checkpoint before running."
    ]
    assert bpy.op_calls == [
        ("mesh.select_all", {"action": "SELECT"}),
        ("mesh.normals_make_consistent", {}),
        ("mesh.remove_doubles", {"threshold": 0.0005}),
        ("mesh.delete_loose", {}),
        (
            "mesh.tris_convert_to_quads",
            {"face_threshold": math.radians(35.0), "shape_threshold": math.radians(35.0)},
        ),
    ]
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["niua:model.generated_cleanup_pass"]
```

- [ ] **Step 3: Write failing unavailable optional-operator test**

Add:

```python
def test_generated_cleanup_pass_reports_unavailable_delete_loose(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    monkeypatch.delattr(type(bpy.ops.mesh), "delete_loose")
    reg = build_default_registry()

    out = dispatch_on_main(reg, "model.generated_cleanup_pass", {"object": "Cube"}, Ctx(bpy))

    assert "delete_loose" not in out["applied"]
    assert out["skipped"] == [{"operator": "mesh.delete_loose", "reason": "unavailable"}]
    assert "mesh.delete_loose was unavailable; inspect for loose generated fragments." in out["warnings"]
    assert _names(bpy.op_calls) == [
        "mesh.select_all",
        "mesh.normals_make_consistent",
        "mesh.remove_doubles",
        "mesh.tris_convert_to_quads",
    ]
```

- [ ] **Step 4: Write failing router exposure test**

Add:

```python
def test_generated_cleanup_pass_is_exposed_in_server_router():
    from niua_blender_mcp.domains import build_router

    specs = {s.name: s for s in build_router().specs()}
    spec = specs["model.generated_cleanup_pass"]
    assert spec.mutates is True
    assert spec.feedback == "viewport"
    assert spec.tier == "curated"
    assert spec.params["face_threshold"].default == 35.0
    assert spec.params["merge_distance"].default == 0.0005
```

- [ ] **Step 5: Run red tests**

Run:

```bash
pytest tests/domains/test_modeling_verbs.py::test_generated_cleanup_pass_runs_available_delete_loose_sequence tests/domains/test_modeling_verbs.py::test_generated_cleanup_pass_reports_unavailable_delete_loose tests/domains/test_modeling_verbs.py::test_generated_cleanup_pass_is_exposed_in_server_router -q
```

Expected: fail because `model.generated_cleanup_pass` is not registered.

- [ ] **Step 6: Implement handler and server spec**

In `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`, add helpers near the top:

```python
def _mesh_object(ctx: Ctx, payload: dict):
    obj_name = payload.get("object")
    if not isinstance(obj_name, str) or not obj_name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(obj_name)
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(PRECONDITION, f"object is not a mesh: {obj_name}")
    return obj


def _workflow_defaults(workflow_id: str) -> tuple[dict, dict]:
    workflow = craft_workflows.get_workflow(workflow_id)
    return workflow, workflow["default_params"]
```

Add:

```python
def _optional_mesh_op(ctx: Ctx, op, name: str, applied: list[str], skipped: list[dict], warnings: list[str]) -> bool:
    if op is None:
        skipped.append({"operator": name, "reason": "unavailable"})
        warnings.append("mesh.delete_loose was unavailable; inspect for loose generated fragments.")
        return False
    try:
        ctx.check_poll(op)
    except BridgeError:
        skipped.append({"operator": name, "reason": "unavailable"})
        warnings.append("mesh.delete_loose was unavailable; inspect for loose generated fragments.")
        return False
    op()
    applied.append(name.split(".")[-1])
    return True
```

Add `generated_cleanup_pass`:

```python
def generated_cleanup_pass(ctx: Ctx, payload: dict) -> dict:
    obj = _mesh_object(ctx, payload)
    workflow, defaults = _workflow_defaults("generated_cleanup.rebuild_noisy_mesh")
    face_threshold = float(payload.get("face_threshold", defaults["face_threshold"]))
    merge_distance = float(payload.get("merge_distance", defaults["merge_distance"]))
    threshold_radians = math.radians(face_threshold)
    applied: list[str] = []
    skipped: list[dict] = []
    warnings = [workflow["cautions"][0]]
    ops = ctx.bpy.ops

    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        applied.append("select_all")
        ctx.check_poll(ops.mesh.normals_make_consistent)
        ops.mesh.normals_make_consistent()
        applied.append("normals_make_consistent")
        ctx.check_poll(ops.mesh.remove_doubles)
        ops.mesh.remove_doubles(threshold=merge_distance)
        applied.append("remove_doubles")
        _optional_mesh_op(ctx, getattr(ops.mesh, "delete_loose", None), "mesh.delete_loose", applied, skipped, warnings)
        ctx.check_poll(ops.mesh.tris_convert_to_quads)
        ops.mesh.tris_convert_to_quads(
            face_threshold=threshold_radians,
            shape_threshold=threshold_radians,
        )
        applied.append("tris_convert_to_quads")

    return {
        "object": obj.name,
        "asset_class": workflow["asset_class"],
        "workflow_id": workflow["id"],
        "applied": applied,
        "skipped": skipped,
        "params": {"face_threshold": face_threshold, "merge_distance": merge_distance},
        "warnings": warnings,
        "postcheck_recommended": ["feedback.topology", "pipeline.gate_check"],
    }
```

Register:

```python
Command("model.generated_cleanup_pass", generated_cleanup_pass, mutates=True, feedback="viewport")
```

In `src/niua_blender_mcp/domains/modeling_verbs.py`, add:

```python
ToolSpec(
    name="model.generated_cleanup_pass",
    category="modeling",
    summary="Clean generated mesh noise: normals, duplicate merge, optional loose deletion, and quad conversion",
    command="model.generated_cleanup_pass",
    params={
        "object": Str(required=True, summary="Generated mesh object to clean"),
        "face_threshold": Float(default=35.0, minimum=0.0, maximum=180.0, summary="Tri-to-quad merge threshold in degrees"),
        "merge_distance": Float(default=0.0005, minimum=0.0, summary="Duplicate merge distance"),
    },
    mutates=True,
    feedback="viewport",
    tier="curated",
)
```

- [ ] **Step 7: Run green tests**

Run:

```bash
pytest tests/domains/test_modeling_verbs.py::test_generated_cleanup_pass_runs_available_delete_loose_sequence tests/domains/test_modeling_verbs.py::test_generated_cleanup_pass_reports_unavailable_delete_loose tests/domains/test_modeling_verbs.py::test_generated_cleanup_pass_is_exposed_in_server_router -q
```

Expected: pass.

- [ ] **Step 8: Commit**

Run:

```bash
git add tests/domains/test_modeling_verbs.py blender_addon/niua_mcp_bridge/domains/modeling_verbs.py src/niua_blender_mcp/domains/modeling_verbs.py
git commit -m "feat: add generated cleanup craft verb"
```

### Task 3: Organic Retopo Prep Composite Verb

**Files:**
- Modify: `tests/domains/test_modeling_verbs.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`
- Modify: `src/niua_blender_mcp/domains/modeling_verbs.py`

**Interfaces:**
- Consumes: `_mesh_object` and `_workflow_defaults` from Task 2.
- Consumes: `organic.silhouette_retopo_prep` workflow defaults from Task 1.
- Produces: add-on handler `organic_retopo_prep(ctx, payload) -> dict`.
- Produces: server spec `model.organic_retopo_prep`.

- [ ] **Step 1: Write failing organic sequence test**

Add:

```python
def test_organic_retopo_prep_runs_non_hard_surface_sequence(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "model.organic_retopo_prep", {"object": "Cube"}, Ctx(bpy))

    assert out["object"] == "Cube"
    assert out["asset_class"] == "organic_prop"
    assert out["workflow_id"] == "organic.silhouette_retopo_prep"
    assert out["applied"] == [
        "select_all",
        "normals_make_consistent",
        "remove_doubles",
        "tris_convert_to_quads",
    ]
    assert out["skipped"] == []
    assert out["params"] == {"face_threshold": 50.0, "merge_distance": 0.0002}
    assert out["warnings"] == ["Do not bevel organic contours as a default cleanup move."]
    assert out["postcheck_recommended"] == ["feedback.topology", "pipeline.gate_check"]
    assert bpy.op_calls == [
        ("mesh.select_all", {"action": "SELECT"}),
        ("mesh.normals_make_consistent", {}),
        ("mesh.remove_doubles", {"threshold": 0.0002}),
        (
            "mesh.tris_convert_to_quads",
            {"face_threshold": math.radians(50.0), "shape_threshold": math.radians(50.0)},
        ),
    ]
    assert "mesh.bevel" not in _names(bpy.op_calls)
    assert "mesh.inset" not in _names(bpy.op_calls)
    assert "mesh.delete_loose" not in _names(bpy.op_calls)
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["niua:model.organic_retopo_prep"]
```

- [ ] **Step 2: Write failing router exposure test**

Add:

```python
def test_organic_retopo_prep_is_exposed_in_server_router():
    from niua_blender_mcp.domains import build_router

    specs = {s.name: s for s in build_router().specs()}
    spec = specs["model.organic_retopo_prep"]
    assert spec.mutates is True
    assert spec.feedback == "viewport"
    assert spec.tier == "curated"
    assert spec.params["face_threshold"].default == 50.0
    assert spec.params["merge_distance"].default == 0.0002
```

- [ ] **Step 3: Run red tests**

Run:

```bash
pytest tests/domains/test_modeling_verbs.py::test_organic_retopo_prep_runs_non_hard_surface_sequence tests/domains/test_modeling_verbs.py::test_organic_retopo_prep_is_exposed_in_server_router -q
```

Expected: fail because `model.organic_retopo_prep` is not registered.

- [ ] **Step 4: Implement handler and server spec**

In `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py`, add:

```python
def organic_retopo_prep(ctx: Ctx, payload: dict) -> dict:
    obj = _mesh_object(ctx, payload)
    workflow, defaults = _workflow_defaults("organic.silhouette_retopo_prep")
    face_threshold = float(payload.get("face_threshold", defaults["face_threshold"]))
    merge_distance = float(payload.get("merge_distance", defaults["merge_distance"]))
    threshold_radians = math.radians(face_threshold)
    applied: list[str] = []
    ops = ctx.bpy.ops

    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        applied.append("select_all")
        ctx.check_poll(ops.mesh.normals_make_consistent)
        ops.mesh.normals_make_consistent()
        applied.append("normals_make_consistent")
        ctx.check_poll(ops.mesh.remove_doubles)
        ops.mesh.remove_doubles(threshold=merge_distance)
        applied.append("remove_doubles")
        ctx.check_poll(ops.mesh.tris_convert_to_quads)
        ops.mesh.tris_convert_to_quads(
            face_threshold=threshold_radians,
            shape_threshold=threshold_radians,
        )
        applied.append("tris_convert_to_quads")

    return {
        "object": obj.name,
        "asset_class": workflow["asset_class"],
        "workflow_id": workflow["id"],
        "applied": applied,
        "skipped": [],
        "params": {"face_threshold": face_threshold, "merge_distance": merge_distance},
        "warnings": [workflow["cautions"][0]],
        "postcheck_recommended": ["feedback.topology", "pipeline.gate_check"],
    }
```

Register:

```python
Command("model.organic_retopo_prep", organic_retopo_prep, mutates=True, feedback="viewport")
```

In `src/niua_blender_mcp/domains/modeling_verbs.py`, add:

```python
ToolSpec(
    name="model.organic_retopo_prep",
    category="modeling",
    summary="Normalize organic topology without hard-surface bevel, inset, or loose-fragment deletion",
    command="model.organic_retopo_prep",
    params={
        "object": Str(required=True, summary="Organic mesh object to prepare for retopo"),
        "face_threshold": Float(default=50.0, minimum=0.0, maximum=180.0, summary="Tri-to-quad merge threshold in degrees"),
        "merge_distance": Float(default=0.0002, minimum=0.0, summary="Light duplicate merge distance"),
    },
    mutates=True,
    feedback="viewport",
    tier="curated",
)
```

- [ ] **Step 5: Run green tests**

Run:

```bash
pytest tests/domains/test_modeling_verbs.py::test_organic_retopo_prep_runs_non_hard_surface_sequence tests/domains/test_modeling_verbs.py::test_organic_retopo_prep_is_exposed_in_server_router -q
pytest tests/domains/test_modeling_verbs.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add tests/domains/test_modeling_verbs.py blender_addon/niua_mcp_bridge/domains/modeling_verbs.py src/niua_blender_mcp/domains/modeling_verbs.py
git commit -m "feat: add organic retopo prep craft verb"
```

### Task 4: Wave 9B Acceptance, Diagram, and Final Verification

**Files:**
- Modify: `tests/test_smoke_headless.py`
- Modify: `docs/layer2-architecture.html`

**Interfaces:**
- Consumes: Task 1 workflow ids and ranks.
- Consumes: Task 2 and Task 3 command outputs.

- [ ] **Step 1: Write failing headless acceptance test**

Add after `test_layer2_wave9a_craft_workflow_acceptance`:

```python
def test_layer2_wave9b_workflow_breadth_acceptance(bridge: BlenderBridge) -> None:
    bridge.call("object.create", {"type": "CUBE", "name": "GeneratedWorkflowHero"})
    bridge.call("object.create", {"type": "CUBE", "name": "OrganicWorkflowHero"})

    bridge.call("pipeline.start", {"object": "GeneratedWorkflowHero", "asset_class": "generated_cleanup"})
    assert bridge.call("pipeline.advance", {"object": "GeneratedWorkflowHero"})["to_stage"] == "repair"
    assert bridge.call("pipeline.advance", {"object": "GeneratedWorkflowHero"})["to_stage"] == "retopo"
    generated_recommendation = bridge.call("craft_workflow.recommend", {"object": "GeneratedWorkflowHero"})
    assert generated_recommendation["recommendations"][0]["id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert generated_recommendation["recommendations"][0]["rank"] == 1
    generated = bridge.call("model.generated_cleanup_pass", {"object": "GeneratedWorkflowHero"})
    assert generated["workflow_id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert generated["asset_class"] == "generated_cleanup"
    assert "remove_doubles" in generated["applied"]
    assert generated["postcheck_recommended"] == ["feedback.topology", "pipeline.gate_check"]
    generated_quality = bridge.call("feedback.quality", {"object": "GeneratedWorkflowHero"})
    assert generated_quality["asset_class"]["id"] == "generated_cleanup"
    generated_gate = bridge.call("pipeline.gate_check", {"object": "GeneratedWorkflowHero", "stage": "retopo"})
    assert generated_gate["asset_class"]["id"] == "generated_cleanup"

    bridge.call("pipeline.start", {"object": "OrganicWorkflowHero", "asset_class": "organic_prop"})
    assert bridge.call("pipeline.advance", {"object": "OrganicWorkflowHero"})["to_stage"] == "repair"
    assert bridge.call("pipeline.advance", {"object": "OrganicWorkflowHero"})["to_stage"] == "retopo"
    organic_recommendation = bridge.call("craft_workflow.recommend", {"object": "OrganicWorkflowHero"})
    assert organic_recommendation["recommendations"][0]["id"] == "organic.silhouette_retopo_prep"
    assert organic_recommendation["recommendations"][0]["rank"] == 1
    organic = bridge.call("model.organic_retopo_prep", {"object": "OrganicWorkflowHero"})
    assert organic["workflow_id"] == "organic.silhouette_retopo_prep"
    assert organic["asset_class"] == "organic_prop"
    assert organic["applied"] == [
        "select_all",
        "normals_make_consistent",
        "remove_doubles",
        "tris_convert_to_quads",
    ]
    assert organic["skipped"] == []
    organic_quality = bridge.call("feedback.quality", {"object": "OrganicWorkflowHero"})
    assert organic_quality["asset_class"]["id"] == "organic_prop"
    organic_gate = bridge.call("pipeline.gate_check", {"object": "OrganicWorkflowHero", "stage": "retopo"})
    assert organic_gate["asset_class"]["id"] == "organic_prop"
```

- [ ] **Step 2: Run red/green acceptance**

Run:

```bash
pytest tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q
```

Expected before Tasks 2-3: fail because the new commands are missing. Expected after Tasks 2-3: pass when Blender is available, otherwise skip under the existing smoke-test rule.

- [ ] **Step 3: Update architecture diagram**

Update `docs/layer2-architecture.html`:

- metric counts should be refreshed with:

```bash
PYTHONPATH=src:blender_addon python - <<'PY'
from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.domains import build_default_registry
print(len(build_router().specs()))
print(len(build_default_registry().names()))
PY
```

- mark Wave 9B as built/current.
- show generated cleanup and organic workflow breadth as built.
- move next wave to UV/bake/material workflow breadth.
- keep hard-surface Wave 9A marked built.

- [ ] **Step 4: Browser-check the diagram**

Run:

```bash
python - <<'PY'
from html.parser import HTMLParser
from pathlib import Path

class Parser(HTMLParser):
    pass

Parser().feed(Path("docs/layer2-architecture.html").read_text(encoding="utf-8"))
print("html_parse_ok")
PY
printf '%s' '[["viewport","1440x1200"],["goto","file:///home/frankyin/Desktop/lab/lab-niua-blender/docs/layer2-architecture.html"],["wait","--load"],["screenshot","--viewport","/tmp/layer2-architecture-wave9b-desktop.png"]]' | /home/frankyin/.agents/skills/gstack/browse/dist/browse chain
printf '%s' '[["viewport","390x1100"],["goto","file:///home/frankyin/Desktop/lab/lab-niua-blender/docs/layer2-architecture.html"],["wait","--load"],["screenshot","--viewport","/tmp/layer2-architecture-wave9b-mobile.png"]]' | /home/frankyin/.agents/skills/gstack/browse/dist/browse chain
```

Expected: HTML parse prints `html_parse_ok`; screenshots are nonblank and readable.

- [ ] **Step 5: Final verification**

Run:

```bash
pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py tests/domains/test_modeling_verbs.py tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q
python scripts/audit_blender_coverage.py --fail-on partial
pytest -q
git diff --check
```

Expected:

- targeted tests pass
- audit reports `partial: 0` and `missing: 0`
- full pytest exits 0
- diff check exits 0

- [ ] **Step 6: Commit**

Run:

```bash
git add tests/test_smoke_headless.py docs/layer2-architecture.html
git commit -m "docs: update Layer 2 workflow breadth map"
```

## Self-Review Checklist

- Registry data exists on both server and add-on sides with exact parity.
- Recommendation output includes stable `rank`.
- `from_scratch_prop` still has no fallback workflow in Wave 9B.
- Generated cleanup reports unavailable `mesh.delete_loose` in `skipped`.
- Organic prep does not call bevel, inset, or delete-loose by default.
- Router and add-on command registry expose both new model verbs.
- Headless acceptance proves generated and organic recommendation -> command -> quality/gate paths.
- Diagram says Wave 9B is current and does not imply UV/bake/material workflow breadth is already built.
