"""Non-mesh geometry domain: curves, text, surfaces, metaballs, grease pencil."""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Str, ToolSpec, Vec3

CURVE_TYPES = ["BEZIER", "BEZIER_CIRCLE", "NURBS_CURVE", "NURBS_CIRCLE", "NURBS_PATH"]
SURFACE_TYPES = ["CURVE", "CIRCLE", "SURFACE", "CYLINDER", "SPHERE", "TORUS"]
METABALL_TYPES = ["BALL", "CAPSULE", "PLANE", "ELLIPSOID", "CUBE"]
GREASE_PENCIL_TYPES = ["EMPTY", "STROKE", "MONKEY", "LINEART_SCENE", "LINEART_COLLECTION", "LINEART_OBJECT"]
TEXT_ALIGN_X = ["LEFT", "CENTER", "RIGHT", "JUSTIFY", "FLUSH"]
TEXT_ALIGN_Y = ["TOP", "TOP_BASELINE", "CENTER", "BOTTOM", "BOTTOM_BASELINE"]

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
    ToolSpec(
        name="geometry.create_text",
        category="geometry",
        summary="Create a text object",
        command="geometry.create_text",
        params={
            "name": Str(default="", summary="Optional object name"),
            "body": Str(default="Text", summary="Text body"),
            "align_x": Enum(TEXT_ALIGN_X, default="LEFT", summary="Horizontal alignment"),
            "align_y": Enum(TEXT_ALIGN_Y, default="TOP_BASELINE", summary="Vertical alignment"),
            "size": Float(default=1.0, minimum=0.0, summary="Text size"),
            "location": Vec3(default=[0.0, 0.0, 0.0], summary="World location [x, y, z]"),
            "rotation": Vec3(default=[0.0, 0.0, 0.0], summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(default=[1.0, 1.0, 1.0], summary="Scale [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="geometry.create_surface",
        category="geometry",
        summary="Create a NURBS surface primitive",
        command="geometry.create_surface",
        params={
            "type": Enum(SURFACE_TYPES, required=True, summary="Surface primitive type"),
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
        name="geometry.create_metaball",
        category="geometry",
        summary="Create a metaball primitive",
        command="geometry.create_metaball",
        params={
            "type": Enum(METABALL_TYPES, default="BALL", summary="Metaball primitive type"),
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
        name="geometry.create_grease_pencil",
        category="geometry",
        summary="Create a grease pencil object",
        command="geometry.create_grease_pencil",
        params={
            "type": Enum(GREASE_PENCIL_TYPES, default="EMPTY", summary="Grease pencil object type"),
            "name": Str(default="", summary="Optional object name"),
            "radius": Float(default=1.0, minimum=0.0, summary="Primitive radius"),
            "use_in_front": Bool(default=False, summary="Draw in front"),
            "location": Vec3(default=[0.0, 0.0, 0.0], summary="World location [x, y, z]"),
            "rotation": Vec3(default=[0.0, 0.0, 0.0], summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(default=[1.0, 1.0, 1.0], summary="Scale [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
