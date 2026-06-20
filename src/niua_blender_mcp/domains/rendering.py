"""Rendering subsystem manifest: cameras, lights, render settings, world, compositor."""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Str, ToolSpec, Vec3

CAMERA_TYPES = ["PERSP", "ORTHO", "PANO"]
LIGHT_TYPES = ["POINT", "SUN", "SPOT", "AREA"]

SPECS = [
    ToolSpec(
        name="camera.create",
        category="camera",
        summary="Create a camera and optionally make it the active scene camera",
        command="camera.create",
        params={
            "name": Str(default="", summary="Optional camera object name"),
            "location": Vec3(default=[0.0, 0.0, 0.0], summary="World location [x, y, z]"),
            "rotation": Vec3(default=[0.0, 0.0, 0.0], summary="Euler rotation in radians [x, y, z]"),
            "lens": Float(default=50.0, minimum=1.0, summary="Perspective focal length in mm"),
            "type": Enum(CAMERA_TYPES, default="PERSP", summary="Camera projection type"),
            "ortho_scale": Float(default=6.0, minimum=0.0, summary="Orthographic camera scale"),
            "clip_start": Float(default=0.1, minimum=0.0, summary="Near clipping distance"),
            "clip_end": Float(default=1000.0, minimum=0.0, summary="Far clipping distance"),
            "active": Bool(default=True, summary="Make this the active scene camera"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="camera.list",
        category="camera",
        summary="List scene cameras and active camera",
        command="camera.list",
        params={},
    ),
    ToolSpec(
        name="camera.report",
        category="camera",
        summary="Report one camera, defaulting to the active scene camera",
        command="camera.report",
        params={"camera": Str(default="", summary="Camera object name")},
    ),
    ToolSpec(
        name="camera.set",
        category="camera",
        summary="Set common camera data properties",
        command="camera.set",
        params={
            "camera": Str(required=True, summary="Camera object name"),
            "lens": Float(minimum=1.0, summary="Perspective focal length in mm"),
            "type": Enum(CAMERA_TYPES, summary="Camera projection type"),
            "ortho_scale": Float(minimum=0.0, summary="Orthographic camera scale"),
            "clip_start": Float(minimum=0.0, summary="Near clipping distance"),
            "clip_end": Float(minimum=0.0, summary="Far clipping distance"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="camera.set_active",
        category="camera",
        summary="Set the active scene camera",
        command="camera.set_active",
        params={"camera": Str(required=True, summary="Camera object name")},
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="light.create",
        category="light",
        summary="Create a light object",
        command="light.create",
        params={
            "type": Enum(LIGHT_TYPES, default="POINT", summary="Light type"),
            "name": Str(default="", summary="Optional light object name"),
            "location": Vec3(default=[0.0, 0.0, 0.0], summary="World location [x, y, z]"),
            "rotation": Vec3(default=[0.0, 0.0, 0.0], summary="Euler rotation in radians [x, y, z]"),
            "energy": Float(default=10.0, minimum=0.0, summary="Light energy"),
            "color": Vec3(default=[1.0, 1.0, 1.0], summary="Light RGB color"),
            "size": Float(minimum=0.0, summary="Area/point light size"),
            "spot_size": Float(minimum=0.0, summary="Spot cone angle in radians"),
            "spot_blend": Float(minimum=0.0, maximum=1.0, summary="Spot edge softness"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="light.list",
        category="light",
        summary="List scene lights",
        command="light.list",
        params={},
    ),
    ToolSpec(
        name="light.report",
        category="light",
        summary="Report one light, or all scene lights if omitted",
        command="light.report",
        params={"light": Str(default="", summary="Light object name")},
    ),
    ToolSpec(
        name="light.set",
        category="light",
        summary="Set common light data properties",
        command="light.set",
        params={
            "light": Str(required=True, summary="Light object name"),
            "energy": Float(minimum=0.0, summary="Light energy"),
            "color": Vec3(summary="Light RGB color"),
            "size": Float(minimum=0.0, summary="Area/point light size"),
            "spot_size": Float(minimum=0.0, summary="Spot cone angle in radians"),
            "spot_blend": Float(minimum=0.0, maximum=1.0, summary="Spot edge softness"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
