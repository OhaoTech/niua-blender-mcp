"""Seed craft verbs (server side): model.retopo_quads."""

from __future__ import annotations

from ..kernel import Float, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="model.retopo_quads",
        category="modeling",
        summary="Convert a mesh to clean quads: tris to quads, consistent normals, merge doubles",
        command="model.retopo_quads",
        params={
            "object": Str(required=True, summary="Mesh object to clean up"),
            "face_threshold": Float(
                default=40.0,
                minimum=0.0,
                maximum=180.0,
                summary="Max angle in degrees to merge tri pairs into quads",
            ),
        },
        mutates=True,
        feedback="viewport",
        tier="curated",
    ),
]
