"""Scene domain manifest: read the scene, create primitives, set transforms."""

from __future__ import annotations

from ..kernel import Enum, Str, ToolSpec, Vec3

PRIMITIVE_TYPES = ["CUBE", "SPHERE", "PLANE", "CYLINDER", "CONE", "EMPTY"]

SPECS = [
    ToolSpec(
        name="scene.info",
        category="scene",
        summary="Summarize the current scene (objects, materials)",
        command="scene.info",
    ),
    ToolSpec(
        name="scene.create_object",
        category="scene",
        summary="Create a primitive object in the scene",
        command="scene.create_object",
        params={
            "type": Enum(PRIMITIVE_TYPES, required=True, summary="Primitive type"),
            "name": Str(summary="Optional object name"),
            "location": Vec3(summary="World location [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="scene.set_transform",
        category="scene",
        summary="Set an object's location/rotation/scale",
        command="scene.set_transform",
        params={
            "object": Str(required=True, summary="Object name"),
            "location": Vec3(summary="World location [x, y, z]"),
            "rotation": Vec3(summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(summary="Scale [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
