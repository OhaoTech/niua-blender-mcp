# Layer 2 Wave 10 Surface Stack Design

Date: 2026-06-26

## Context

Wave 9A introduced the first craft workflow path for `hard_surface_prop`.
Wave 9B proved that the workflow registry can cover multiple asset classes
without turning into a generic recipe executor:

```text
asset_class + stage
        |
        v
craft_workflow.recommend
        |
        v
explicit curated command
        |
        v
feedback.quality / pipeline.gate_check
```

The next unproven area is the later production stack. The pipeline already has
`uv`, `bake`, and `material` stages; it already has objective gates for each;
and the add-on already has low-level UV and shading primitives. What is missing
is one discoverable senior workflow that carries an asset from UV preparation
through material-stack readiness as a single gated slice.

## Goal

Build Wave 10 as one vertical slice across:

```text
uv -> bake -> material
```

The first class-specific target is `hard_surface_prop`, because Wave 9A already
proved hard-surface craft detail. Wave 10 should make a hard-surface asset
arrive at the later production stages and run a single explicit command that:

1. creates usable packed UVs,
2. prepares the required game PBR map slots,
3. returns structured post-check guidance, and
4. lets `pipeline.gate_check` pass `uv`, `bake`, and `material` as the pipeline advances.

## Non-Goals

- No generic workflow executor.
- No dynamic recipe runner.
- No new pipeline stages.
- No new asset class.
- No true high-poly-to-low-poly bake, cage projection, or ray baking yet.
- No material artistry, procedural texture generation, or lookdev judgment loop.
- No UV seam intelligence beyond existing Blender smart unwrap and packing primitives.
- No Wave 10 support claim for `organic_prop`, `generated_cleanup`, or `from_scratch_prop`.

## Architecture

Add one new workflow record to the mirrored craft workflow registries:

```text
craft_workflows registry
        |
        +-- hard_surface.panel_detail_pass             built in Wave 9A
        +-- generated_cleanup.rebuild_noisy_mesh       built in Wave 9B
        +-- organic.silhouette_retopo_prep             built in Wave 9B
        +-- hard_surface.surface_stack_for_game        new in Wave 10
```

The existing discovery surface stays unchanged:

- `craft_workflow.list`
- `craft_workflow.describe`
- `craft_workflow.recommend`

The new workflow is only recommended at the UV entry stage:

```text
asset_class=hard_surface_prop stage=uv
        |
        v
hard_surface.surface_stack_for_game
```

No fallback workflow should be invented for unsupported classes. If an organic,
generated-cleanup, or from-scratch asset reaches `uv`, Wave 10 may return no
workflow until a later wave adds class-specific surface guidance.

The command prepares downstream bake and material readiness, but the registry
does not advertise it as a `bake` or `material` stage recommendation. That keeps
the workflow from re-running UV unwraps after the asset has already advanced.

## Workflow Record

### `hard_surface.surface_stack_for_game`

Asset class: `hard_surface_prop`

Entry stage: `uv`

Downstream gates prepared by the command: `bake`, `material`

Purpose: prepare a hard-surface prop for downstream game-material validation by
creating packed UVs and a complete PBR texture-slot stack that satisfies the
existing deterministic UV, bake, and material gates.

Required tools:

- `surface.prepare_game_material_stack`
- `uv.smart_unwrap`
- `uv.average_islands_scale`
- `uv.pack_islands`
- `shading.prepare_pbr_maps`
- `feedback.quality`
- `pipeline.gate_check`

Default params:

```python
{
    "angle_limit": 66.0,
    "island_margin": 0.02,
    "pack_margin": 0.01,
    "texture_size": 1024,
    "maps": "BASE_COLOR,NORMAL,ROUGHNESS,AO,CAVITY",
}
```

Gate targets:

- `uv.has_uvs`
- `uv.out_of_bounds_loops`
- `uv.overlap_detected`
- `uv.stretch_ratio`
- `material.bake_maps_present`
- `material.data_maps_non_color`
- `material.pbr_maps_present`
- `material.textures_within_size`
- `material.atlas_ready`

Recipe steps:

1. select all mesh faces and run smart UV projection,
2. average island scale,
3. pack UV islands with a margin,
4. create or reuse a node-based material,
5. create required PBR image slots for base color, normal, roughness, AO, and cavity,
6. wire map slots into the principled material stack where existing primitives support it,
7. return recommended post-checks for `feedback.quality` and `pipeline.gate_check`.

Cautions:

- This prepares map slots and material readiness; it is not a true high-poly bake.
- Smart unwrap is a practical default, not senior seam placement.
- Always verify UV stretch, overlap, and material readiness with gates after running.

## Public Tool Surface

### `surface.prepare_game_material_stack`

Curated mutating workflow command. The `surface` prefix means Layer 2
surface-production workflow, not Blender's NURBS Surface object type.

Parameters:

- `object`: required mesh object name.
- `material`: optional material name, default `<object>_PBR`.
- `prefix`: optional image/map prefix, default object name.
- `angle_limit`: float degrees, default `66.0`, range `0..89`.
- `island_margin`: float, default `0.02`, range `0..1`.
- `pack_margin`: float, default `0.01`, range `0..1`.
- `texture_size`: integer, default `1024`, range `1..8192`.
- `maps`: comma-separated map list, default `BASE_COLOR,NORMAL,ROUGHNESS,AO,CAVITY`.

The add-on handler is explicit Python orchestration, not a dynamic workflow
runner. It should call the existing domain handlers or the same underlying
operations in this order:

1. `uv.smart_unwrap`
2. `uv.average_islands_scale`
3. `uv.pack_islands`
4. `shading.prepare_pbr_maps`
5. `feedback.quality`

Return:

```json
{
  "object": "Crate",
  "asset_class": "hard_surface_prop",
  "workflow_id": "hard_surface.surface_stack_for_game",
  "applied": [
    "uv.smart_unwrap",
    "uv.average_islands_scale",
    "uv.pack_islands",
    "shading.prepare_pbr_maps",
    "feedback.quality"
  ],
  "skipped": [],
  "params": {
    "angle_limit": 66.0,
    "island_margin": 0.02,
    "pack_margin": 0.01,
    "texture_size": 1024,
    "maps": ["BASE_COLOR", "NORMAL", "ROUGHNESS", "AO", "CAVITY"]
  },
  "material": "Crate_PBR",
  "maps": ["BASE_COLOR", "NORMAL", "ROUGHNESS", "AO", "CAVITY"],
  "quality": {
    "uv": {
      "has_uvs": true,
      "overlap_detected": false
    },
    "material": {
      "bake_maps_present": true,
      "pbr_maps_present": true,
      "atlas_ready": true
    }
  },
  "warnings": [
    "This prepares map slots and material readiness; it is not a true high-poly bake."
  ],
  "postcheck_recommended": ["feedback.quality", "pipeline.gate_check"]
}
```

If a required step cannot run, the command should raise the existing clean
`BridgeError` from the called handler. Do not hide required failures in
`skipped`. `skipped` is reserved for future optional behavior; Wave 10 does not
need optional steps.

## Data Flow

Expected live sequence:

```text
object.create
pipeline.start(asset_class="hard_surface_prop")
pipeline.advance -> repair
pipeline.advance -> retopo
pipeline.advance -> uv
craft_workflow.recommend(object=...)
surface.prepare_game_material_stack(object=...)
pipeline.gate_check(stage="uv")       -> pass
pipeline.advance                      -> bake
pipeline.gate_check(stage="bake")     -> pass
pipeline.advance                      -> material
pipeline.gate_check(stage="material") -> pass
```

The command does not advance the pipeline itself. The agent remains responsible
for calling `pipeline.gate_check` and `pipeline.advance`, preserving the gated
process discipline from earlier waves.

## Error Handling

- Missing `object` returns `INVALID_PARAMS`.
- Non-mesh objects return `PRECONDITION`.
- UV operator `poll()` failure returns the existing `PRECONDITION`.
- Unsupported `maps` values return `INVALID_PARAMS`.
- Invalid `texture_size`, margins, or angle limits return `INVALID_PARAMS`.
- Material/image creation failures return the clean Blender bridge error from
  `shading.prepare_pbr_maps`.
- The command must not catch and downgrade required step failures to warnings.

## Testing Strategy

### Registry and Router

- Server and add-on craft workflow registries remain identical.
- `WORKFLOW_IDS` includes `hard_surface.surface_stack_for_game`.
- `craft_workflow.list(asset_class="hard_surface_prop", stage="uv")` returns the new workflow.
- `craft_workflow.recommend(asset_class="hard_surface_prop", stage="uv")` returns the new workflow with `rank == 1`.
- `from_scratch_prop`, `organic_prop`, and `generated_cleanup` do not get Wave 10 fallback workflows.
- The server router exposes `surface.prepare_game_material_stack`.
- The add-on registry exposes `surface.prepare_game_material_stack`.

### Fake-Bpy Unit Tests

Use the existing recording fake-bpy pattern to prove operator and handler order:

```text
uv.smart_project
uv.average_islands_scale
uv.pack_islands
shading.prepare_pbr_maps / material + image node creation
feedback.quality
```

The tests should assert:

- returned `workflow_id`,
- `asset_class`,
- `applied`,
- empty `skipped`,
- parsed/default params,
- material name,
- created maps,
- `postcheck_recommended`,
- one undo push after successful mutation.

### Headless Acceptance

Add `test_layer2_wave10_surface_stack_acceptance`:

1. create a hard-surface cube,
2. start and advance the pipeline to `uv`,
3. assert recommendation id and rank,
4. run `surface.prepare_game_material_stack`,
5. assert UV quality reports UVs,
6. assert `pipeline.gate_check(stage="uv")` passes,
7. advance to `bake`,
8. assert bake gate passes,
9. advance to `material`,
10. assert material gate passes.

### Diagram Verification

Update `docs/layer2-architecture.html`:

- mark Wave 10 built/current,
- show the new `uv -> bake -> material` surface-stack path,
- move the next wave to from-scratch/blockout workflow or true bake/cage depth,
- do not imply that true high-poly baking is built.

Verify with:

- HTML parser,
- desktop screenshot,
- mobile screenshot,
- no horizontal overflow at mobile width.

## Implementation Boundary

Wave 10 can add a new domain module if that keeps responsibilities clear:

```text
src/niua_blender_mcp/domains/surface.py
blender_addon/niua_mcp_bridge/domains/surface.py
tests/domains/test_surface.py
```

It should not put this workflow into the low-level `uv` or `shading` modules
unless the implementation stays smaller and clearer there. The preferred
boundary is a `surface` domain because the command spans UV, map slots, and
material-readiness checks.

## Verification Commands

The final implementation must pass:

```bash
pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py tests/domains/test_surface.py tests/test_smoke_headless.py::test_layer2_wave10_surface_stack_acceptance -q
python scripts/audit_blender_coverage.py --fail-on partial
pytest -q
git diff --check
```

## Future Waves

After Wave 10, good follow-up candidates are:

- true high-poly-to-low-poly baking with cage/projection checks,
- class-specific surface workflows for generated cleanup and organic props,
- from-scratch blockout-to-game workflow,
- deeper material lookdev and perceptual critique.
