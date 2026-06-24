# Layer 2 Wave 9A Craft Workflow Spine Design

Date: 2026-06-24

## Context

Wave 8 made the Layer 2 game-asset pipeline asset-class aware. The pipeline can now carry targets for `hard_surface_prop`, `organic_prop`, `generated_cleanup`, and `from_scratch_prop`, and those targets flow through quality checks, gates, and knowledge packs.

That is still a map, not a craft move. The next useful layer is a small workflow spine that can answer: given this asset class and pipeline stage, what senior workflow should the agent run next?

## Goal

Add a deterministic craft workflow registry plus one real hard-surface workflow vertical slice:

```text
asset_class + stage
        |
        v
craft_workflow.recommend
        |
        v
hard_surface.panel_detail_pass
        |
        v
feedback.quality / pipeline.gate_check
```

Wave 9A should prove the recommendation-to-action path end to end without building a generic workflow executor or all future workflows.

## Non-Goals

- No generic dynamic recipe executor.
- No full asset generation from text briefs.
- No organic, generated-cleanup, or from-scratch workflow breadth yet.
- No new pipeline stage unless a later wave adds gates for it.
- No perceptual judge changes.
- No claim that one detail pass produces a finished senior-quality asset.

## Architecture

Add mirrored craft workflow registries in the server package and Blender add-on. The registries are mirrored, like asset classes, because the server and Blender add-on run in different Python contexts.

```text
src/niua_blender_mcp/craft_workflows.py
blender_addon/niua_mcp_bridge/core/craft_workflows.py
        |
        +-- craft_workflow.list
        +-- craft_workflow.describe
        +-- craft_workflow.recommend
        |
        v
hard_surface.panel_detail_pass
```

The registry is structured data plus small lookup helpers:

- `list_workflows() -> list[dict]`
- `get_workflow(workflow_id: str) -> dict`
- `recommend_workflows(asset_class: str | None, stage: str | None, state: dict | None = None) -> list[dict]`

The initial registry contains one workflow:

```python
{
    "id": "hard_surface.panel_detail_pass",
    "label": "Hard-surface panel detail pass",
    "asset_class": "hard_surface_prop",
    "stages": ["repair", "retopo"],
    "summary": "Add readable hard-surface panel recesses, chamfer sharp edges, and normalize topology.",
    "required_tools": [
        "model.recess_panels",
        "model.bevel_edges",
        "model.retopo_quads",
    ],
    "default_params": {
        "inset": 0.08,
        "depth": 0.04,
        "angle": 30.0,
        "width": 0.02,
        "segments": 2,
        "face_threshold": 40.0,
    },
    "gate_targets": ["topology.ngons", "topology.quad_ratio", "topology.non_manifold_edges"],
    "recipe_steps": [
        "recess broad faces into readable panel detail",
        "bevel sharp edges with a small support chamfer",
        "normalize topology back toward quads and consistent normals",
    ],
    "outputs": ["panel recesses", "edge chamfers", "quad-normalized topology"],
    "cautions": [
        "Run on a copied/checkpointed mesh when preserving the original silhouette matters.",
        "Re-check topology gates after the pass; beveling and inset operations can create extra poles.",
    ],
}
```

## Public Tool Surface

### `craft_workflow.list`

Read-only. Optional filters:

- `asset_class`
- `stage`

Returns summary records only: id, label, asset class, stages, summary, and required tools.

### `craft_workflow.describe`

Read-only. Parameters:

- `workflow`: required workflow id.

Returns the complete workflow record.

### `craft_workflow.recommend`

Read-only. Parameters:

- `object`: optional mesh object name. When present and pipeline state exists, the command may use that state.
- `asset_class`: optional asset-class id. Explicit value wins over pipeline state.
- `stage`: optional pipeline stage. Explicit value wins over pipeline state.

Returns ranked recommendation records. In Wave 9A, ranking is deterministic:

1. exact asset-class and exact stage match
2. exact asset-class and no stage match

If nothing matches, return an empty list plus a reason string; do not invent a fallback workflow.

### `hard_surface.panel_detail_pass`

Curated mutating craft verb. Parameters:

- `object`: required mesh object name.
- `inset`: float, default `0.08`, minimum `0`.
- `depth`: float, default `0.04`, minimum `0`.
- `angle`: float degrees, default `30.0`, range `0..180`.
- `width`: float, default `0.02`, minimum `0`.
- `segments`: integer, default `2`, range `1..12`.
- `face_threshold`: float degrees, default `40.0`, range `0..180`.

The add-on handler runs in edit mode with the object active and selected:

1. select all faces
2. inset faces with individual panel recess depth
3. deselect all
4. select sharp edges by angle
5. bevel selected edges
6. select all
7. convert tris to quads
8. make normals consistent
9. merge doubles

Return:

```json
{
  "object": "Crate",
  "asset_class": "hard_surface_prop",
  "workflow_id": "hard_surface.panel_detail_pass",
  "applied": [
    "select_all",
    "inset",
    "edges_select_sharp",
    "bevel",
    "tris_convert_to_quads",
    "normals_make_consistent",
    "remove_doubles"
  ],
  "params": {
    "inset": 0.08,
    "depth": 0.04,
    "angle": 30.0,
    "width": 0.02,
    "segments": 2,
    "face_threshold": 40.0
  },
  "warnings": [
    "Re-check topology gates after the pass; beveling and inset operations can create extra poles."
  ]
}
```

## Verification

- Server and add-on workflow registries have identical records.
- Router exposes `craft_workflow.list`, `craft_workflow.describe`, `craft_workflow.recommend`, and `hard_surface.panel_detail_pass`.
- Add-on registry exposes the same command names.
- `craft_workflow.recommend(asset_class="hard_surface_prop", stage="retopo")` returns `hard_surface.panel_detail_pass`.
- `craft_workflow.recommend(asset_class="organic_prop", stage="retopo")` returns no workflow in Wave 9A.
- Fake-bpy tests prove `hard_surface.panel_detail_pass` runs the expected operator sequence.
- Headless Blender smoke proves the command is callable on a cube and quality/gate checks still run afterward.

## Future Waves

Wave 9B can add generated-cleanup workflows. Wave 9C can add UV/bake/material workflow breadth. A later wave can introduce a generic workflow executor only after two or more real workflows prove common orchestration needs.
