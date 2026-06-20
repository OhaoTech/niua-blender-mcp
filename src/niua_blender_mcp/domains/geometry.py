"""Non-mesh geometry domain: curves, text, surfaces, metaballs, grease pencil."""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec, Vec3

CURVE_TYPES = ["BEZIER", "BEZIER_CIRCLE", "NURBS_CURVE", "NURBS_CIRCLE", "NURBS_PATH"]
SURFACE_TYPES = ["CURVE", "CIRCLE", "SURFACE", "CYLINDER", "SPHERE", "TORUS"]
METABALL_TYPES = ["BALL", "CAPSULE", "PLANE", "ELLIPSOID", "CUBE"]
GREASE_PENCIL_TYPES = ["EMPTY", "STROKE", "MONKEY", "LINEART_SCENE", "LINEART_COLLECTION", "LINEART_OBJECT"]
TEXT_ALIGN_X = ["LEFT", "CENTER", "RIGHT", "JUSTIFY", "FLUSH"]
TEXT_ALIGN_Y = ["TOP", "TOP_BASELINE", "CENTER", "BOTTOM", "BOTTOM_BASELINE"]
CURVE_DIMENSIONS = ["2D", "3D"]
CURVE_FILL_MODES = ["FULL", "FRONT", "BACK", "HALF"]

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
    ToolSpec(
        name="geometry.set_curve",
        category="geometry",
        summary="Set curve-like geometry data fields",
        command="geometry.set_curve",
        params={
            "object": Str(required=True, summary="Object name"),
            "bevel_depth": Float(minimum=0.0, summary="Bevel depth"),
            "bevel_resolution": Int(minimum=0, maximum=32, summary="Bevel resolution"),
            "extrude": Float(minimum=0.0, summary="Extrude amount"),
            "resolution_u": Int(minimum=1, maximum=1024, summary="Viewport resolution"),
            "render_resolution_u": Int(minimum=0, maximum=1024, summary="Render resolution"),
            "dimensions": Enum(CURVE_DIMENSIONS, summary="Curve dimensions"),
            "fill_mode": Enum(CURVE_FILL_MODES, summary="Fill mode"),
            "use_fill_caps": Bool(summary="Fill bevel caps"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="geometry.set_text",
        category="geometry",
        summary="Set text object fields",
        command="geometry.set_text",
        params={
            "object": Str(required=True, summary="Text object name"),
            "body": Str(summary="Text body"),
            "align_x": Enum(TEXT_ALIGN_X, summary="Horizontal alignment"),
            "align_y": Enum(TEXT_ALIGN_Y, summary="Vertical alignment"),
            "size": Float(minimum=0.0, summary="Text size"),
            "space_line": Float(minimum=0.0, summary="Line spacing"),
            "offset_x": Float(summary="Horizontal text offset"),
            "offset_y": Float(summary="Vertical text offset"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="geometry.convert_to_mesh",
        category="geometry",
        summary="Convert a non-mesh geometry object to a mesh",
        command="geometry.convert_to_mesh",
        params={
            "object": Str(required=True, summary="Object name"),
            "name": Str(default="", summary="Optional converted mesh name"),
            "keep_original": Bool(default=False, summary="Keep the source object and create a mesh copy"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
