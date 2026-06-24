"""Layer 2 pipeline tool manifest."""

from __future__ import annotations

from ..asset_classes import ASSET_CLASS_IDS
from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="pipeline.start",
        category="pipeline",
        summary="Start a gated Layer 2 game-asset pipeline run for an object",
        command="pipeline.start",
        params={
            "object": Str(required=True, summary="Object to track through the pipeline"),
            "profile": Str(default="game_asset", summary="Pipeline profile"),
            "asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
        },
    ),
    ToolSpec(
        name="pipeline.status",
        category="pipeline",
        summary="Read pipeline state for one object, or all active pipeline runs",
        command="pipeline.status",
        params={
            "object": Str(summary="Object to inspect; all runs if omitted"),
        },
    ),
    ToolSpec(
        name="pipeline.gate_check",
        category="pipeline",
        summary="Evaluate objective gates for the current or named pipeline stage",
        command="pipeline.gate_check",
        params={
            "object": Str(required=True, summary="Object whose pipeline gates should be checked"),
            "stage": Str(summary="Stage to check; defaults to the object's current stage"),
            "triangle_budget": Int(default=5000, minimum=0, summary="Optimize-stage triangle budget"),
            "material_budget": Int(default=4, minimum=0, summary="Optimize-stage material budget"),
            "texture_budget": Int(default=8, minimum=0, summary="Optimize-stage texture budget"),
            "min_lods": Int(minimum=0, summary="Optimize-stage minimum LOD count"),
            "max_lod_triangle_ratio": Float(
                default=0.75,
                minimum=0.0,
                maximum=1.0,
                summary="Optimize-stage maximum LOD triangle ratio relative to the source",
            ),
            "max_lod_bounds_delta": Float(
                default=0.1,
                minimum=0.0,
                maximum=1.0,
                summary="Optimize-stage maximum relative bounds delta for LOD silhouette preservation",
            ),
            "min_collision_hulls": Int(default=1, minimum=0, summary="Optimize-stage minimum collision hull count"),
            "max_collision_oversize_ratio": Float(
                default=0.5,
                minimum=0.0,
                summary="Optimize-stage maximum collision union oversize ratio",
            ),
            "max_texture_size": Int(default=2048, minimum=1, summary="Bake/material-stage maximum texture dimension"),
            "export_profile": Str(default="GENERIC", summary="Export profile: GENERIC, GODOT, UNREAL, or CUSTOM"),
            "export_format": Str(default="GLB", summary="Planned export format for export-preflight profile validation"),
            "export_y_up": Bool(summary="Planned +Y-up export option for export-preflight profile validation"),
            "allowed_formats": Str(default="", summary="CUSTOM export profile allowed formats"),
            "require_collision": Bool(summary="CUSTOM export profile collision-proxy requirement"),
            "require_applied_transforms": Bool(summary="CUSTOM export profile applied-transform requirement"),
            "name_regex": Str(default="", summary="CUSTOM export profile object-name regex"),
        },
    ),
    ToolSpec(
        name="pipeline.advance",
        category="pipeline",
        summary="Gate-check the current stage and advance to the next stage when gates pass",
        command="pipeline.advance",
        params={
            "object": Str(required=True, summary="Object whose pipeline should advance"),
        },
    ),
    ToolSpec(
        name="pipeline.rollback",
        category="pipeline",
        summary="Restore a stage entry checkpoint and move the pipeline pointer back",
        command="pipeline.rollback",
        params={
            "object": Str(required=True, summary="Object whose pipeline checkpoint should be restored"),
            "stage": Str(summary="Stage checkpoint to restore; defaults to current stage"),
        },
        mutates=True,
    ),
    ToolSpec(
        name="pipeline.self_critique",
        category="pipeline",
        summary="Explain failed stage gates with grounded repair guidance",
        command="pipeline.self_critique",
        params={
            "object": Str(required=True, summary="Object whose current stage should be critiqued"),
            "stage": Str(summary="Stage to critique; defaults to current stage"),
            "attempt": Int(default=1, minimum=1, maximum=20, summary="Current bounded retry attempt"),
            "max_attempts": Int(default=3, minimum=1, maximum=20, summary="Retry budget for this stage"),
        },
    ),
]
