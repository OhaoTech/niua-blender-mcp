"""Scene domain handlers: read the scene, create primitives, set transforms."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, BridgeError

_PRIMITIVES = {
    "CUBE": ("mesh", "primitive_cube_add"),
    "SPHERE": ("mesh", "primitive_uv_sphere_add"),
    "PLANE": ("mesh", "primitive_plane_add"),
    "CYLINDER": ("mesh", "primitive_cylinder_add"),
    "CONE": ("mesh", "primitive_cone_add"),
    "EMPTY": ("object", "empty_add"),
}


def _vec(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise BridgeError(INVALID_PARAMS, "expected a 3-item array")
    return [float(item) for item in value]


def _created(bpy: Any, before: set[str]) -> Any:
    obj = getattr(bpy.context, "object", None)
    if obj is not None and getattr(obj, "name", "") not in before:
        return obj
    for candidate in reversed(list(bpy.context.scene.objects)):
        if getattr(candidate, "name", "") not in before:
            return candidate
    raise BridgeError(HANDLER_ERROR, "no object was created")


def scene_info(ctx: Ctx, payload: dict) -> dict:
    bpy = ctx.bpy
    scene = bpy.context.scene
    return {
        "scene": getattr(scene, "name", "Scene"),
        "objects": [ctx.object_summary(o) for o in getattr(scene, "objects", [])],
        "materials": sorted(getattr(bpy.data, "materials", {}).keys()),
    }


def create_object(ctx: Ctx, payload: dict) -> dict:
    bpy = ctx.bpy
    otype = str(payload.get("type", "")).upper()
    if otype not in _PRIMITIVES:
        raise BridgeError(INVALID_PARAMS, f"unsupported object type: {otype}")
    location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    before = {getattr(o, "name", "") for o in bpy.context.scene.objects}
    group, op = _PRIMITIVES[otype]
    getattr(getattr(bpy.ops, group), op)(location=location)
    obj = _created(bpy, before)
    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
    return ctx.object_summary(obj)


def set_transform(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("object")
    if not isinstance(name, str):
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(name)
    if "location" in payload:
        obj.location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    if "rotation" in payload:
        obj.rotation_euler = _vec(payload.get("rotation"), [0.0, 0.0, 0.0])
    if "scale" in payload:
        obj.scale = _vec(payload.get("scale"), [1.0, 1.0, 1.0])
    return ctx.object_summary(obj)


COMMANDS = [
    Command("scene.info", scene_info, mutates=False),
    Command("scene.create_object", create_object, mutates=True, feedback="viewport"),
    Command("scene.set_transform", set_transform, mutates=True, feedback="viewport"),
]
