"""Deeper eyes (server side): topology overlay."""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

_VIEWS = ["front", "back", "left", "right", "top", "bottom", "persp"]

SPECS = [
    ToolSpec(
        name="feedback.topology",
        category="feedback",
        summary="Render a topology overlay: n-gons red, tris orange, quads grey, plus wireframe",
        command="feedback.topology",
        params={
            "object": Str(summary="Mesh to inspect (defaults to active)"),
            "view": Enum(_VIEWS, default="persp", summary="Named view to render from"),
            "res": Int(default=768, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
]
