"""Object domain manifest: lifecycle, transforms, origins, and bounds."""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec, Vec3

OBJECT_TYPES = ["CUBE", "SPHERE", "PLANE", "CYLINDER", "CONE", "TORUS", "MONKEY", "EMPTY"]
END_FILL_TYPES = ["NGON", "TRIFAN", "NOTHING"]
EMPTY_DISPLAY_TYPES = ["PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE", "CUBE", "SPHERE", "CONE", "IMAGE"]
EULER_MODES = ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"]
ORIGIN_TYPES = [
    "GEOMETRY_ORIGIN",
    "ORIGIN_GEOMETRY",
    "ORIGIN_CURSOR",
    "ORIGIN_CENTER_OF_MASS",
    "ORIGIN_CENTER_OF_VOLUME",
]
ORIGIN_CENTERS = ["MEDIAN", "BOUNDS"]

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
        name="object.duplicate",
        category="object",
        summary="Duplicate an object",
        command="object.duplicate",
        params={
            "object": Str(required=True, summary="Object name"),
            "name": Str(default="", summary="Optional duplicate name"),
            "linked": Bool(default=False, summary="Share source object data"),
            "offset": Vec3(default=[0.0, 0.0, 0.0], summary="Location offset [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="object.delete",
        category="object",
        summary="Delete one or more objects",
        command="object.delete",
        params={"objects": Str(required=True, summary="Comma-separated object names")},
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="object.rename",
        category="object",
        summary="Rename an object",
        command="object.rename",
        params={
            "object": Str(required=True, summary="Object name"),
            "name": Str(required=True, summary="New object name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="object.transform_set",
        category="object",
        summary="Set an object's transform fields",
        command="object.transform_set",
        params={
            "object": Str(required=True, summary="Object name"),
            "location": Vec3(summary="World location [x, y, z]"),
            "rotation": Vec3(summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(summary="Scale [x, y, z]"),
            "delta_location": Vec3(summary="Delta location [x, y, z]"),
            "delta_rotation": Vec3(summary="Delta Euler rotation [x, y, z]"),
            "delta_scale": Vec3(summary="Delta scale [x, y, z]"),
            "rotation_mode": Enum(EULER_MODES, summary="Euler rotation mode"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="object.transform_apply",
        category="object",
        summary="Apply an object's transform",
        command="object.transform_apply",
        params={
            "object": Str(required=True, summary="Object name"),
            "location": Bool(default=True, summary="Apply location"),
            "rotation": Bool(default=True, summary="Apply rotation"),
            "scale": Bool(default=True, summary="Apply scale"),
            "properties": Bool(default=True, summary="Apply object data properties"),
            "isolate_users": Bool(default=False, summary="Make shared data single-user first"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="object.origin_set",
        category="object",
        summary="Set an object's origin",
        command="object.origin_set",
        params={
            "object": Str(required=True, summary="Object name"),
            "type": Enum(ORIGIN_TYPES, default="ORIGIN_GEOMETRY", summary="Origin operation"),
            "center": Enum(ORIGIN_CENTERS, default="MEDIAN", summary="Origin center mode"),
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
    ToolSpec(
        name="object.bake_transfer",
        category="object",
        summary="Bake high->low detail (normal/AO) from a source mesh into a target mesh's maps",
        command="object.bake_transfer",
        params={
            "source": Str(required=True, summary="High-poly source object"),
            "target": Str(required=True, summary="Low-poly target object (must have UVs)"),
            "maps": Str(default="NORMAL,AO", summary="Comma-separated maps to bake: NORMAL, AO"),
            "size": Int(default=1024, minimum=1, maximum=8192, summary="Baked image size in pixels"),
            "ray_distance": Float(default=0.01, minimum=0.0, summary="Cage extrusion / ray distance"),
        },
        mutates=True,
        feedback="viewport",
        timeout_tier="heavy",
    ),
    ToolSpec(
        name="object.shrinkwrap",
        category="object",
        summary="Snap a mesh's vertices onto a target object's surface via a SHRINKWRAP modifier",
        command="object.shrinkwrap",
        params={
            "object": Str(required=True, summary="Mesh object to snap onto the target surface"),
            "target": Str(required=True, summary="Target object supplying the surface to snap onto"),
            "offset": Float(default=0.0, summary="Distance to offset the snapped surface along its normal"),
            "apply": Bool(default=True, summary="Apply the shrinkwrap modifier immediately"),
        },
        mutates=True,
        feedback="viewport",
        timeout_tier="heavy",
    ),
]
