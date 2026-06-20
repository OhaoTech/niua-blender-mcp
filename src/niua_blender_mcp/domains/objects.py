"""Object domain manifest: lifecycle, transforms, origins, and bounds."""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec, Vec3

OBJECT_TYPES = ["CUBE", "SPHERE", "PLANE", "CYLINDER", "CONE", "TORUS", "MONKEY", "EMPTY"]
END_FILL_TYPES = ["NGON", "TRIFAN", "NOTHING"]
EMPTY_DISPLAY_TYPES = ["PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE", "CUBE", "SPHERE", "CONE", "IMAGE"]

SPECS = [
    ToolSpec(
        name="object.create",
        category="object",
        summary="Create a common mesh primitive or empty",
        command="object.create",
        params={
            "type": Enum(OBJECT_TYPES, required=True, summary="Object primitive type"),
            "name": Str(default="", summary="Optional object name"),
            "location": Vec3(default=[0.0, 0.0, 0.0], summary="World location [x, y, z]"),
            "rotation": Vec3(default=[0.0, 0.0, 0.0], summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(default=[1.0, 1.0, 1.0], summary="Scale [x, y, z]"),
            "size": Float(default=2.0, minimum=0.0, summary="Size for cube, plane, monkey"),
            "radius": Float(default=1.0, minimum=0.0, summary="Radius for sphere or empty display"),
            "vertices": Int(default=32, minimum=3, maximum=256, summary="Vertices for cylinder/cone/sphere"),
            "depth": Float(default=2.0, minimum=0.0, summary="Depth for cylinder/cone"),
            "radius1": Float(default=1.0, minimum=0.0, summary="Cone base radius"),
            "radius2": Float(default=0.0, minimum=0.0, summary="Cone top radius"),
            "major_radius": Float(default=1.0, minimum=0.0, summary="Torus major radius"),
            "minor_radius": Float(default=0.25, minimum=0.0, summary="Torus minor radius"),
            "major_segments": Int(default=48, minimum=3, maximum=512, summary="Torus major segments"),
            "minor_segments": Int(default=12, minimum=3, maximum=256, summary="Torus minor segments"),
            "end_fill_type": Enum(END_FILL_TYPES, default="NGON", summary="Cylinder/cone cap fill"),
            "calc_uvs": Bool(default=True, summary="Generate primitive UVs when supported"),
            "empty_display_type": Enum(
                EMPTY_DISPLAY_TYPES,
                default="PLAIN_AXES",
                summary="Empty display type",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="object.transform_get",
        category="object",
        summary="Read an object's transform state",
        command="object.transform_get",
        params={"object": Str(required=True, summary="Object name")},
    ),
    ToolSpec(
        name="object.bounds",
        category="object",
        summary="Read an object's local and world bounds",
        command="object.bounds",
        params={"object": Str(required=True, summary="Object name")},
    ),
]
