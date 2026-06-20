"""Non-mesh geometry domain: curves, text, surfaces, metaballs, grease pencil."""

from __future__ import annotations

from ..kernel import Enum, Float, Str, ToolSpec, Vec3

CURVE_TYPES = ["BEZIER", "BEZIER_CIRCLE", "NURBS_CURVE", "NURBS_CIRCLE", "NURBS_PATH"]

SPECS = [
    ToolSpec(
        name="geometry.create_curve",
        category="geometry",
        summary="Create a curve primitive",
        command="geometry.create_curve",
        params={
            "type": Enum(CURVE_TYPES, required=True, summary="Curve primitive type"),
            "name": Str(default="", summary="Optional object name"),
            "radius": Float(default=1.0, minimum=0.0, summary="Primitive radius"),
            "location": Vec3(default=[0.0, 0.0, 0.0], summary="World location [x, y, z]"),
            "rotation": Vec3(default=[0.0, 0.0, 0.0], summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(default=[1.0, 1.0, 1.0], summary="Scale [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="geometry.report",
        category="geometry",
        summary="Report non-mesh geometry object data",
        command="geometry.report",
        params={"object": Str(required=True, summary="Object name")},
    ),
]
