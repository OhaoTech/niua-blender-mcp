# Layer 2 Wave 8 Asset-Class Profiles Design

Date: 2026-06-24

## Context

Layer 2 now has one gated game-asset pipeline:

```text
intake -> repair -> retopo -> uv -> bake -> material -> optimize -> export_preflight -> exported
```

Waves 1-7 made that spine observable, resumable, self-critiquing, and objectively gated. The remaining Wave 8 item on the architecture map is asset-class breadth: hard-surface, organic/sculpt, generated cleanup, and from-scratch prop briefs.

Wave 8 should not build four complete artists at once. It should make the existing spine class-aware so every later craft verb has explicit targets to hit.

## Goal

Add deterministic asset-class profiles that can be selected at pipeline start and reused by quality checks, gate checks, knowledge guidance, and scorecards.

The first profile set is:

- `hard_surface_prop`
- `organic_prop`
- `generated_cleanup`
- `from_scratch_prop`

Each profile defines objective thresholds and guidance for the same existing pipeline stages. The profile changes the targets; it does not fork the pipeline.

## Non-Goals

- No full from-scratch asset generation in Wave 8.
- No sculpt brush automation beyond existing generated/reflection access.
- No separate organic pipeline.
- No ML/RL profile tuning.
- No engine-specific naming. Engine conventions remain in export profiles.

## Architecture

Add mirrored profile registries in the server package and the Blender add-on, with parity tests proving the ids, versions, defaults, and gate overrides stay aligned. They are mirrored instead of imported from one shared file because the server and add-on are deployed in different Python contexts.

```text
asset_class.list / describe
          |
          v
mirrored asset profile registries
          |
          +-- pipeline.start(asset_class=...)
          +-- feedback.quality(asset_class=...)
          +-- pipeline.gate_check(asset_class=...)
          +-- knowledge.load(stage, asset_class=...)
```

The registry is plain structured data plus helper functions:

- `list_asset_classes() -> list[dict]`
- `get_asset_class(name) -> dict`
- `resolve_asset_class(payload, state=None) -> dict`
- `apply_asset_class_defaults(payload, stage, state=None) -> dict`

The bridge layer uses the same profile names and values as the server specs. The pipeline state stores the chosen `asset_class` and `profile_version` so later gate checks can use them without repeating the parameter and so scorecards remain auditable after defaults evolve.

## Profile Shape

Each profile has:

- `id`: stable API name.
- `profile_version`: integer version for auditability.
- `label`: short human label.
- `summary`: one-line use case.
- `defaults`: default parameters for `feedback.quality` / `pipeline.gate_check`.
- `gate_overrides`: targeted replacements for existing gate definitions, keyed by stage and metric path.
- `stage_targets`: stage-specific threshold notes.
- `guidance`: class-specific guidance used by `knowledge.load` and self-critique.

Gate overrides do not create separate pipelines. They clone the base stage gate list and replace only the named gate paths. For example:

```python
"gate_overrides": {
    "retopo": {
        "topology.quad_ratio": {"op": ">=", "value": 0.90},
    },
    "uv": {
        "uv.stretch_ratio": {"op": "<=", "value": 2.5},
    },
}
```

If an override references a path that does not exist in the base stage gates, implementation must fail tests rather than silently ignore it.

Initial profiles:

```python
hard_surface_prop = {
    "profile_version": 1,
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
}

organic_prop = {
    "profile_version": 1,
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
}

generated_cleanup = {
    "profile_version": 1,
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
}

from_scratch_prop = {
    "profile_version": 1,
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
}
```

Explicit user parameters override profile defaults. That preserves the current ability to tune a gate for a specific asset.

## Public Tool Surface

### `asset_class.list`

Read-only. Returns the available classes with id, label, and summary.

### `asset_class.describe`

Read-only. Parameters:

- `asset_class`: required string/enum.

Returns the complete profile: defaults, gate overrides, stage targets, and guidance.

### `pipeline.start`

Add optional `asset_class`, default `hard_surface_prop`.

The response and pipeline state both make the selected class visible, including when the default was applied:

```json
{
  "profile": "game_asset",
  "asset_class": "hard_surface_prop",
  "profile_version": 1,
  "asset_class_defaulted": true
}
```

### `feedback.quality`

Add optional `asset_class`.

When present, quality metrics use profile defaults for missing budget/threshold parameters and return:

```json
"asset_class": {
  "id": "hard_surface_prop",
  "profile_version": 1,
  "label": "Hard-surface prop",
  "effective_defaults": {
    "triangle_budget": 5000,
    "material_budget": 4
  },
  "applied_gate_overrides": {}
}
```

### `pipeline.gate_check`

Add optional `asset_class`. If omitted, use the pipeline state's stored class. If the state has no class, use `hard_surface_prop`.

Explicit gate-check parameters override class defaults.

The returned gate list includes any class-specific gate override already applied, and the result includes:

```json
"asset_class": {
  "id": "generated_cleanup",
  "profile_version": 1,
  "effective_defaults": {},
  "applied_gate_overrides": {
    "retopo": {
      "topology.quad_ratio": {"op": ">=", "value": 0.98}
    }
  }
}
```

### `knowledge.load`

Add optional `asset_class`. Returned recommendations include the class summary and class-specific guidance for the requested stage.

## Data Flow

1. Agent starts a pipeline with `pipeline.start(object="Crate", asset_class="generated_cleanup")`.
2. Pipeline state records the class.
3. Agent calls `pipeline.gate_check(object="Crate", stage="optimize")`.
4. Gate check resolves the stored class, applies profile defaults, applies stage gate overrides, then calls `feedback.quality`.
5. Quality metrics include both normal metrics and the applied asset-class metadata.
6. Failed gates are explained by `pipeline.self_critique`, with knowledge guidance augmented by asset-class guidance.

## Error Handling

- Unknown asset class returns `invalid_params` on bridge commands and validation failure on server specs.
- Missing `asset_class` uses `hard_surface_prop`.
- Explicit numeric params always override profile defaults.
- Invalid `gate_overrides` fail during registry tests and cannot be shipped.
- Server/add-on profile drift fails parity tests.
- Profile data is read-only; tools must return copies.

## Testing

Unit tests:

- asset-class registry lists and describes all four profiles.
- unknown class fails cleanly.
- explicit params override profile defaults.
- `pipeline.start` persists asset class in state.
- `feedback.quality(asset_class=...)` applies class defaults.
- `pipeline.gate_check` uses stored class when no class is passed.
- `pipeline.gate_check` applies class-specific retopo and UV gate overrides.
- returned quality/gate results include `asset_class`, `profile_version`, `effective_defaults`, and `applied_gate_overrides`.
- `knowledge.load(stage, asset_class=...)` returns class guidance.
- server and add-on profile registries have matching ids, versions, defaults, and gate overrides.

Acceptance tests:

- Same synthetic object passes `organic_prop` triangle budget and fails `from_scratch_prop` triangle budget.
- Same optimize gate uses different LOD/collision thresholds for different classes.
- Same retopo metrics pass `organic_prop` and fail `generated_cleanup` because the quad-ratio gate differs.
- Router exposes `asset_class.list` and `asset_class.describe`.
- Add-on registry exposes matching commands.

Docs:

- Update `docs/layer2-architecture.html` to mark Wave 8 built.
- Move the next roadmap item to deeper craft verbs / asset-class workflows.

## Implementation Notes

Keep the implementation deliberately small:

- One profile module in the add-on core.
- One mirrored profile module in the server package for specs/tests.
- One curated domain manifest: `src/niua_blender_mcp/domains/asset_class.py`.
- One add-on command domain: `blender_addon/niua_mcp_bridge/domains/asset_class.py`.
- Minimal changes to `feedback`, `pipeline`, and `knowledge`.

The profile registry is a target system, not an automation system. Wave 8 creates the target map; later waves can add class-specific craft verbs that work toward those targets.
