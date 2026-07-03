"""Feedback domain manifest: the agent's eyes.

The anti-blob: judge form from multiple angles, not one lucky shot. All read-only
(``mutates=False``); each renders through a dedicated hidden capture camera so the
user's viewport never moves, and degrades to ``available: false`` headless / no-GPU.
"""

from __future__ import annotations

from ..asset_classes import ASSET_CLASS_IDS
from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec

_VIEWS = ["current", "front", "back", "left", "right", "top", "bottom", "persp"]
_SHADING = ["SOLID", "WIREFRAME", "MATERIAL", "RENDERED"]

SPECS = [
    ToolSpec(
        name="feedback.capture",
        category="feedback",
        summary="Render one view (named or the live scene camera) to a PNG the agent can see",
        command="feedback.capture",
        params={
            "object": Str(summary="Object to frame; whole scene if omitted"),
            "view": Enum(_VIEWS, default="current", summary="Named view or 'current' scene camera"),
            "shading": Enum(_SHADING, default="SOLID", summary="SOLID/WIREFRAME (workbench) or MATERIAL/RENDERED (EEVEE)"),
            "res": Int(default=768, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
    ToolSpec(
        name="feedback.capture_views",
        category="feedback",
        summary="Render a multi-angle preset (the anti-blob) as several images",
        command="feedback.capture_views",
        params={
            "object": Str(summary="Object to frame; whole scene if omitted"),
            "preset": Enum(
                ["ortho4", "ortho6", "orbit4"],
                default="ortho4",
                summary="ortho4=[front,right,top,persp], ortho6=six axes, orbit4=4 orbit angles",
            ),
            "shading": Enum(_SHADING, default="SOLID", summary="Workbench (SOLID/WIREFRAME) or EEVEE (MATERIAL/RENDERED)"),
            "res": Int(default=768, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
    ToolSpec(
        name="feedback.silhouette",
        category="feedback",
        summary="Flat silhouette from preset angles + proportion/symmetry — the form eye.",
        command="feedback.silhouette",
        params={
            "object": Str(summary="Object to frame; defaults to active"),
            "preset": Enum(
                ["ortho4", "ortho6", "orbit4"],
                default="ortho4",
                summary="ortho4=[front,right,top,persp], ortho6=six axes, orbit4=4 orbit angles",
            ),
            "res": Int(default=768, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
    ToolSpec(
        name="feedback.turntable",
        category="feedback",
        summary="Orbit the object/scene and return a sequence of images",
        command="feedback.turntable",
        params={
            "object": Str(summary="Object to orbit; whole scene if omitted"),
            "count": Int(default=6, minimum=2, maximum=24, summary="Number of evenly-spaced orbit frames"),
            "shading": Enum(_SHADING, default="SOLID", summary="Workbench (SOLID/WIREFRAME) or EEVEE (MATERIAL/RENDERED)"),
            "res": Int(default=768, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
    ToolSpec(
        name="feedback.critique",
        category="feedback",
        summary="One observe call to judge a model: multi-angle images + mesh/UV report bundled",
        command="feedback.critique",
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
        name="feedback.quality",
        category="feedback",
        summary="Objective quality metrics for a mesh: topology, UVs, orientation, symmetry, proportion, scale, engine/material readiness (read-only)",
        command="feedback.quality",
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
        name="feedback.capture_intake",
        category="feedback",
        summary="Record the do-no-harm baseline: fixed-frame ortho alpha silhouettes + bbox + a session checkpoint",
        command="feedback.capture_intake",
        params={"object": Str(summary="Mesh object to baseline (defaults to active)")},
    ),
]
