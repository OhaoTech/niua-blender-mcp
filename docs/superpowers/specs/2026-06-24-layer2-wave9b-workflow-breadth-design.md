# Layer 2 Wave 9B Workflow Breadth Design

Date: 2026-06-24

## Context

Wave 9A proved the first craft workflow path:

```text
asset_class + stage -> craft_workflow.recommend -> hard_surface.panel_detail_pass -> feedback.quality / pipeline.gate_check
```

That path is now real for `hard_surface_prop`, but a single class does not prove the architecture generalizes. Wave 9B expands the workflow registry to two more asset classes and adds real composite verbs for each.

## Goal

Add workflow breadth for:

- `generated_cleanup`
- `organic_prop`

The outcome is not a finished artist for either class. The outcome is a proven, testable pattern for class-specific craft moves beyond hard-surface modeling.

## Non-Goals

- No generic workflow executor.
- No dynamic recipe runner.
- No UV, bake, or material workflow breadth in this wave.
- No new pipeline stages.
- No sculpt brush automation.
- No destructive simplification that claims to preserve final quality without gates.

## Architecture

Wave 9B extends the existing mirrored workflow registries:

```text
craft_workflows registry
        |
        +-- hard_surface.panel_detail_pass        built in Wave 9A
        +-- generated_cleanup.rebuild_noisy_mesh  new in Wave 9B
        +-- organic.silhouette_retopo_prep        new in Wave 9B
```

The existing `craft_workflow.list`, `craft_workflow.describe`, and `craft_workflow.recommend` tools stay the public discovery surface. The recommendation helper keeps deterministic matching:

1. exact asset class + exact stage
2. exact asset class, no stage match
3. no fallback for unsupported asset classes

Every recommendation record includes stable `rank`, starting at `1`. Registry order is the ranking order for records with the same match quality. Wave 9B must test rank now so future multi-workflow ordering is not implicit.

Recommendation records have this shape:

```json
{
  "id": "generated_cleanup.rebuild_noisy_mesh",
  "rank": 1,
  "match": "asset_class+stage",
  "asset_class": "generated_cleanup",
  "stages": ["repair", "retopo"],
  "required_tools": ["model.generated_cleanup_pass", "model.retopo_quads", "feedback.topology"]
}
```

## New Workflow Records

### `generated_cleanup.rebuild_noisy_mesh`

Asset class: `generated_cleanup`

Stages: `repair`, `retopo`

Purpose: strip the most common generated-mesh noise before strict retopo gates, while reporting every optional cleanup step that could not run.

Required tools:

- `model.generated_cleanup_pass`
- `model.retopo_quads`
- `feedback.topology`

Default params:

```python
{
    "face_threshold": 35.0,
    "merge_distance": 0.0005,
}
```

Recipe steps:

1. select all mesh elements
2. make normals consistent
3. merge duplicate/near-duplicate vertices
4. delete loose generated fragments where Blender exposes a safe operator
5. convert compatible triangles back to quads
6. re-check strict generated-cleanup topology gates

Cautions:

- Generated cleanup can erase intentional tiny detail; checkpoint before running.
- A pass that makes topology cleaner can still damage silhouette; inspect after gates.

### `organic.silhouette_retopo_prep`

Asset class: `organic_prop`

Stages: `repair`, `retopo`

Purpose: normalize organic/sculpt-derived topology without adding hard-surface detail operations.

Required tools:

- `model.organic_retopo_prep`
- `model.retopo_quads`
- `feedback.topology`

Default params:

```python
{
    "face_threshold": 50.0,
    "merge_distance": 0.0002,
}
```

Recipe steps:

1. select all mesh elements
2. make normals consistent
3. lightly merge duplicate vertices
4. convert compatible triangles to quads with a more relaxed threshold
5. leave silhouette-preserving topology decisions to the retopo gate and visual review

Forbidden default operations:

- no bevel
- no panel inset
- no loose-fragment deletion

Cautions:

- Do not bevel organic contours as a default cleanup move.
- Keep poles and triangles away from visible silhouette and deformation-like flow regions.

## Shared Implementation Boundary

Wave 9B may add tiny shared helpers inside `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py` only when they remove direct duplication from the three craft verbs. Acceptable helpers:

- `_mesh_object(ctx, payload) -> object`: validates required `object`, resolves the Blender object, and enforces `type == "MESH"`.
- `_workflow_defaults(workflow_id) -> dict`: returns workflow defaults from the registry.

Do not add a generic workflow executor. Do not represent workflow recipe steps as callable dynamic instructions. The new verbs remain explicit Python handlers with named Blender operators.

## Public Tool Surface

No new workflow-discovery tools are required. These existing tools must expose the new records:

- `craft_workflow.list`
- `craft_workflow.describe`
- `craft_workflow.recommend`

Two new curated craft verbs are added:

### `model.generated_cleanup_pass`

Parameters:

- `object`: required mesh object name.
- `face_threshold`: float degrees, default `35.0`, range `0..180`.
- `merge_distance`: float, default `0.0005`, minimum `0`.

Runs in edit mode with the object active and selected:

1. `mesh.select_all(action="SELECT")`
2. `mesh.normals_make_consistent()`
3. `mesh.remove_doubles(threshold=merge_distance)`
4. `mesh.delete_loose()` if the operator exists and polls successfully
5. `mesh.tris_convert_to_quads(face_threshold=..., shape_threshold=...)`

Return:

```json
{
  "object": "Blob",
  "asset_class": "generated_cleanup",
  "workflow_id": "generated_cleanup.rebuild_noisy_mesh",
  "applied": [
    "select_all",
    "normals_make_consistent",
    "remove_doubles",
    "delete_loose",
    "tris_convert_to_quads"
  ],
  "skipped": [],
  "params": {
    "face_threshold": 35.0,
    "merge_distance": 0.0005
  },
  "warnings": [
    "Generated cleanup can erase intentional tiny detail; checkpoint before running."
  ],
  "postcheck_recommended": ["feedback.topology", "pipeline.gate_check"]
}
```

If `mesh.delete_loose` is unavailable, skip it and make the skipped path visible:

```json
{
  "applied": ["select_all", "normals_make_consistent", "remove_doubles", "tris_convert_to_quads"],
  "skipped": [{"operator": "mesh.delete_loose", "reason": "unavailable"}],
  "warnings": [
    "Generated cleanup can erase intentional tiny detail; checkpoint before running.",
    "mesh.delete_loose was unavailable; inspect for loose generated fragments."
  ]
}
```

The fake-bpy tests must cover both the normal available path and the unavailable optional-operator path. The live smoke test only requires the command to succeed.

### `model.organic_retopo_prep`

Parameters:

- `object`: required mesh object name.
- `face_threshold`: float degrees, default `50.0`, range `0..180`.
- `merge_distance`: float, default `0.0002`, minimum `0`.

Runs in edit mode with the object active and selected:

1. `mesh.select_all(action="SELECT")`
2. `mesh.normals_make_consistent()`
3. `mesh.remove_doubles(threshold=merge_distance)`
4. `mesh.tris_convert_to_quads(face_threshold=..., shape_threshold=...)`

Return:

```json
{
  "object": "Rock",
  "asset_class": "organic_prop",
  "workflow_id": "organic.silhouette_retopo_prep",
  "applied": [
    "select_all",
    "normals_make_consistent",
    "remove_doubles",
    "tris_convert_to_quads"
  ],
  "skipped": [],
  "params": {
    "face_threshold": 50.0,
    "merge_distance": 0.0002
  },
  "warnings": [
    "Do not bevel organic contours as a default cleanup move."
  ],
  "postcheck_recommended": ["feedback.topology", "pipeline.gate_check"]
}
```

## Testing

### Registry

- Server and add-on workflow registries match exactly.
- `WORKFLOW_IDS` contains exactly:
  - `generated_cleanup.rebuild_noisy_mesh`
  - `hard_surface.panel_detail_pass`
  - `organic.silhouette_retopo_prep`
- `craft_workflow.recommend(asset_class="generated_cleanup", stage="retopo")` returns the generated cleanup workflow.
- `craft_workflow.recommend(asset_class="organic_prop", stage="retopo")` returns the organic workflow.
- `craft_workflow.recommend(asset_class="from_scratch_prop", stage="retopo")` returns no fallback.
- Every returned recommendation includes stable `rank`.
- When one workflow matches, its `rank` is exactly `1`.

### Domain Surface

- Router exposes:
  - `model.generated_cleanup_pass`
  - `model.organic_retopo_prep`
- Add-on registry exposes matching handlers.
- Both specs are `mutates=True`, `feedback="viewport"`, `tier="curated"`.

### Fake-Bpy Operator Sequences

`model.generated_cleanup_pass` asserts:

```python
[
    ("mesh.select_all", {"action": "SELECT"}),
    ("mesh.normals_make_consistent", {}),
    ("mesh.remove_doubles", {"threshold": 0.0005}),
    ("mesh.delete_loose", {}),
    ("mesh.tris_convert_to_quads", {"face_threshold": radians(35.0), "shape_threshold": radians(35.0)}),
]
```

Also test the unavailable optional operator path:

- fake `mesh.delete_loose` is missing or polls false
- output includes `{"operator": "mesh.delete_loose", "reason": "unavailable"}` in `skipped`
- output omits `"delete_loose"` from `applied`
- output includes the warning `mesh.delete_loose was unavailable; inspect for loose generated fragments.`

`model.organic_retopo_prep` asserts:

```python
[
    ("mesh.select_all", {"action": "SELECT"}),
    ("mesh.normals_make_consistent", {}),
    ("mesh.remove_doubles", {"threshold": 0.0002}),
    ("mesh.tris_convert_to_quads", {"face_threshold": radians(50.0), "shape_threshold": radians(50.0)}),
]
```

Also assert that organic prep does not call:

- `mesh.bevel`
- `mesh.inset`
- `mesh.delete_loose`

### Headless Acceptance

One smoke test should:

1. create `GeneratedWorkflowHero`
2. start pipeline with `asset_class="generated_cleanup"`
3. advance to `retopo`
4. recommend workflow and assert `generated_cleanup.rebuild_noisy_mesh`
5. run `model.generated_cleanup_pass`
6. run `feedback.quality` and `pipeline.gate_check`
7. repeat the recommendation and command path for `OrganicWorkflowHero` with `asset_class="organic_prop"`

## Diagram Update

Update `docs/layer2-architecture.html` so Wave 9B is the current map:

- Wave 9A remains built.
- Wave 9B shows generated cleanup and organic workflow breadth.
- Next wave becomes UV/bake/material workflow breadth.

## Definition of Done

- Unit tests pass for workflow registry, workflow domain tools, and modeling verbs.
- Recommendation output includes stable `rank`.
- Skipped optional Blender operators are visible and tested.
- Organic prep tests assert no bevel, inset, or delete-loose default operation.
- Headless Wave 9B smoke acceptance passes or skips under the existing Blender skip rule.
- `pytest -q` exits 0.
- `python scripts/audit_blender_coverage.py --fail-on partial` exits 0.
- `docs/layer2-architecture.html` parses and renders cleanly on desktop and mobile.
