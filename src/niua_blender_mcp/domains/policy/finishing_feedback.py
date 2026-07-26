"""Finishing feedback domain manifest: the policy-laden judgment channel.

The five ``feedback.*`` policy tools (moved out of ``domains/feedback.py``, which keeps
the generic capture/capture_views/silhouette/turntable eyes) plus ``io.profile_validate``
(moved out of ``domains/io.py``, whose other handlers only ever touch files). All six
encode NIUA game-asset policy -- asset-class budgets, objective gate definitions,
export-profile conventions, do-no-harm preservation -- so they live in the finishing
layer and import ``ASSET_CLASS_IDS`` from ``..finishing.asset_classes`` freely. That
import direction (finishing -> interface) is allowed; the reverse is not.

Tool names and params are byte-identical to their pre-split definitions -- this is a
pure module reorganization, not a surface change (``tests/test_parity.py`` guards it).
"""

from __future__ import annotations

from ...finishing.asset_classes import ASSET_CLASS_IDS
from ...kernel import Bool, Enum, Float, Int, Str, ToolSpec
from ..feedback import _SHADING
from ..io import EXPORT_FORMATS

#: Export-profile conventions for io.profile_validate (moved out of domains/io.py).
EXPORT_PROFILES = ["GENERIC", "GODOT", "UNREAL", "CUSTOM"]

SPECS = [
    ToolSpec(
        name="feedback.quality",
        category="feedback",
        summary="Objective quality metrics for a mesh: topology, UVs, orientation, symmetry, proportion, scale, engine/material readiness (read-only)",
        command="feedback.quality",
        timeout_tier="heavy",
        params={
            "object": Str(summary="Mesh object to measure (defaults to active)"),
            "asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
            "triangle_budget": Int(minimum=0, summary="Maximum triangles for the optimize gate"),
            "material_budget": Int(minimum=0, summary="Maximum material slots for the optimize gate"),
            "texture_budget": Int(minimum=0, summary="Maximum unique image textures for the optimize gate"),
            "min_lods": Int(minimum=0, summary="Minimum detected LOD variants for the optimize gate"),
            "max_lod_triangle_ratio": Float(
                minimum=0.0,
                maximum=1.0,
                summary="Maximum allowed triangle ratio for each LOD relative to the source",
            ),
            "max_lod_bounds_delta": Float(
                minimum=0.0,
                maximum=1.0,
                summary="Maximum relative bounds delta allowed for LOD silhouette preservation",
            ),
            "min_collision_hulls": Int(minimum=0, summary="Minimum detected collision hull count"),
            "max_collision_oversize_ratio": Float(
                minimum=0.0,
                summary="Maximum collision union oversize ratio relative to the source bounds",
            ),
            "max_texture_size": Int(minimum=1, summary="Maximum texture dimension for material atlas readiness"),
            "export_profile": Str(default="GENERIC", summary="Export profile: GENERIC, GODOT, UNREAL, or CUSTOM"),
            "export_format": Str(default="GLB", summary="Planned export format for profile validation"),
            "export_y_up": Bool(summary="Planned +Y-up export option for profile validation"),
            "allowed_formats": Str(default="", summary="CUSTOM export profile allowed formats"),
            "require_collision": Bool(summary="CUSTOM export profile collision-proxy requirement"),
            "require_applied_transforms": Bool(summary="CUSTOM export profile applied-transform requirement"),
            "name_regex": Str(default="", summary="CUSTOM export profile object-name regex"),
        },
    ),
    ToolSpec(
        name="feedback.critique",
        category="feedback",
        summary="One observe call to judge a model: multi-angle images + mesh/UV report bundled",
        command="feedback.critique",
        timeout_tier="heavy",
        params={
            "object": Str(summary="Object to judge; whole scene if omitted"),
            "preset": Enum(
                ["ortho4", "ortho6", "orbit4"],
                default="ortho4",
                summary="Multi-angle preset for the images (the anti-blob)",
            ),
            "shading": Enum(_SHADING, default="SOLID", summary="Workbench (SOLID/WIREFRAME) or EEVEE (MATERIAL/RENDERED)"),
            "res": Int(default=640, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
    ToolSpec(
        name="feedback.capture_intake",
        category="feedback",
        summary="Record the do-no-harm baseline: fixed-frame ortho alpha silhouettes + bbox + a session checkpoint",
        command="feedback.capture_intake",
        timeout_tier="heavy",
        params={"object": Str(summary="Mesh object to baseline (defaults to active)")},
    ),
    ToolSpec(
        name="feedback.preservation",
        category="feedback",
        summary="Do-no-harm metric: mean/min silhouette IoU of current form vs the stored intake baseline + bbox delta (read-only, no revert)",
        command="feedback.preservation",
        timeout_tier="heavy",
        params={"object": Str(summary="Object with a stored intake baseline (defaults to active)")},
    ),
    ToolSpec(
        name="feedback.readiness",
        category="feedback",
        summary="Objective game-ready scorecard: fraction of all objective gates passed, order-free + deduped (no judge, no images)",
        command="feedback.readiness",
        timeout_tier="heavy",
        params={
            "object": Str(summary="Mesh object to score (defaults to active)"),
            "asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
        },
    ),
    ToolSpec(
        name="io.profile_validate",
        category="io",
        summary="Validate an object against a parameterized export profile without exporting",
        command="io.profile_validate",
        params={
            "object": Str(required=True, summary="Object to validate"),
            "profile": Enum(EXPORT_PROFILES, default="GENERIC", summary="Export convention profile"),
            "format": Enum(EXPORT_FORMATS, default="GLB", summary="Planned export format"),
            "y_up": Bool(summary="Planned +Y-up export option"),
            "allowed_formats": Str(default="", summary="CUSTOM override: comma-separated allowed formats"),
            "require_collision": Bool(default=False, summary="CUSTOM override: require a collision proxy"),
            "min_lods": Int(default=0, minimum=0, maximum=8, summary="CUSTOM override: minimum detected LOD variants"),
            "require_applied_transforms": Bool(default=True, summary="CUSTOM override: require identity/applied transforms"),
            "name_regex": Str(default="", summary="CUSTOM override: object-name regex"),
        },
    ),
]
