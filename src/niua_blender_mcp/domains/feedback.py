"""Feedback domain manifest: the agent's eyes.

The anti-blob: judge form from multiple angles, not one lucky shot. All read-only
(``mutates=False``); each renders through a dedicated hidden capture camera so the
user's viewport never moves, and degrades to ``available: false`` headless / no-GPU.
"""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

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
        summary="Objective quality metrics for a mesh: topology, UVs, symmetry, proportion, scale (read-only)",
        command="feedback.quality",
        params={
            "object": Str(summary="Mesh object to measure (defaults to active)"),
        },
    ),
]
