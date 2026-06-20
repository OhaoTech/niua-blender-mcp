"""Seed craft verbs (server side): model.retopo_quads."""

from __future__ import annotations

from ..kernel import Float, Int, Str, ToolSpec

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
    ToolSpec(
        name="model.bevel_edges",
        category="modeling",
        summary="Select sharp edges by angle and bevel them as a single hard-surface craft step",
        command="model.bevel_edges",
        params={
            "object": Str(required=True, summary="Mesh object to bevel"),
            "angle": Float(
                default=30.0,
                minimum=0.0,
                maximum=180.0,
                summary="Sharp-edge threshold in degrees",
            ),
            "width": Float(default=0.02, minimum=0.0, summary="Bevel width"),
            "segments": Int(default=2, minimum=1, maximum=12, summary="Bevel segment count"),
        },
        mutates=True,
        feedback="viewport",
        tier="curated",
    ),
    ToolSpec(
        name="model.recess_panels",
        category="modeling",
        summary="Inset all faces and push the inset inward to create recessed hard-surface panels",
        command="model.recess_panels",
        params={
            "object": Str(required=True, summary="Mesh object to panel-recess"),
            "inset": Float(default=0.08, minimum=0.0, summary="Panel inset thickness"),
            "depth": Float(default=0.04, minimum=0.0, summary="Inward panel recess depth"),
        },
        mutates=True,
        feedback="viewport",
        tier="curated",
    ),
]
