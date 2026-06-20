"""Rendering subsystem handlers: cameras, lights, render settings, world, compositor."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, NOT_FOUND, PRECONDITION, BridgeError


def _vec(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    return [float(item) for item in value]


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in value]
    except Exception:  # noqa: BLE001 - partial/fake values
        return []


def _scene_objects(ctx: Ctx) -> list[Any]:
    return list(getattr(ctx.bpy.context.scene, "objects", []) or [])


def _find_object(ctx: Ctx, name: Any) -> Any:
    if not isinstance(name, str) or not name:
        raise BridgeError(NOT_FOUND, "object name is required")
    obj = getattr(getattr(ctx.bpy.data, "objects", None), "get", lambda _name: None)(name)
    if obj is None:
        obj = next((candidate for candidate in _scene_objects(ctx) if getattr(candidate, "name", None) == name), None)
    if obj is None:
        raise BridgeError(NOT_FOUND, f"object not found: {name}")
    return obj


def _created(ctx: Ctx, before: set[str], kind: str) -> Any:
    obj = getattr(ctx.bpy.context, "object", None)
    if obj is not None and getattr(obj, "name", "") not in before and getattr(obj, "type", None) == kind:
        return obj
    for candidate in reversed(_scene_objects(ctx)):
        if getattr(candidate, "name", "") not in before and getattr(candidate, "type", None) == kind:
            return candidate
    raise BridgeError(HANDLER_ERROR, f"no {kind.lower()} object was created")


def _require_type(obj: Any, kind: str) -> Any:
    if getattr(obj, "type", None) != kind:
        raise BridgeError(
            PRECONDITION,
            f"object is not a {kind.lower()}: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    return obj


def _resolve_camera(ctx: Ctx, name: Any = "") -> Any:
    if isinstance(name, str) and name:
        return _require_type(_find_object(ctx, name), "CAMERA")
    camera = getattr(ctx.bpy.context.scene, "camera", None)
    if camera is None:
        raise BridgeError(PRECONDITION, "no active scene camera; pass 'camera'")
    return _require_type(camera, "CAMERA")


def _camera_entry(ctx: Ctx, obj: Any) -> dict:
    data = getattr(obj, "data", None)
    return {
        "camera": getattr(obj, "name", ""),
        "active": getattr(ctx.bpy.context.scene, "camera", None) is obj,
        "location": _float_list(getattr(obj, "location", [])),
        "rotation": _float_list(getattr(obj, "rotation_euler", [])),
        "type": getattr(data, "type", None),
        "lens": float(getattr(data, "lens", 0.0) or 0.0),
        "ortho_scale": float(getattr(data, "ortho_scale", 0.0) or 0.0),
        "clip_start": float(getattr(data, "clip_start", 0.0) or 0.0),
        "clip_end": float(getattr(data, "clip_end", 0.0) or 0.0),
        "sensor_width": float(getattr(data, "sensor_width", 0.0) or 0.0),
    }


def _set_camera_data(obj: Any, payload: dict, *, defaults: bool = False) -> None:
    data = getattr(obj, "data", None)
    values = {
        "lens": float(payload.get("lens", 50.0)),
        "type": str(payload.get("type", "PERSP")),
        "ortho_scale": float(payload.get("ortho_scale", 6.0)),
        "clip_start": float(payload.get("clip_start", 0.1)),
        "clip_end": float(payload.get("clip_end", 1000.0)),
    }
    for key, value in values.items():
        if defaults or key in payload:
            setattr(data, key, value)


def camera_create(ctx: Ctx, payload: dict) -> dict:
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    rotation = _vec(payload.get("rotation"), [0.0, 0.0, 0.0])
    ctx.bpy.ops.object.camera_add(location=location, rotation=rotation)
    obj = _created(ctx, before, "CAMERA")
    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
    _set_camera_data(obj, payload, defaults=True)
    if bool(payload.get("active", True)):
        ctx.bpy.context.scene.camera = obj
    return _camera_entry(ctx, obj)


def camera_list(ctx: Ctx, payload: dict) -> dict:
    cameras = [_camera_entry(ctx, obj) for obj in _scene_objects(ctx) if getattr(obj, "type", None) == "CAMERA"]
    active = getattr(ctx.bpy.context.scene, "camera", None)
    return {"active": getattr(active, "name", None) if active is not None else None, "count": len(cameras), "cameras": cameras}


def camera_report(ctx: Ctx, payload: dict) -> dict:
    return _camera_entry(ctx, _resolve_camera(ctx, payload.get("camera", "")))


def camera_set(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_camera(ctx, payload.get("camera"))
    _set_camera_data(obj, payload)
    return _camera_entry(ctx, obj)


def camera_set_active(ctx: Ctx, payload: dict) -> dict:
    ctx.bpy.context.scene.camera = _resolve_camera(ctx, payload.get("camera"))
    return camera_list(ctx, {})


def _resolve_light(ctx: Ctx, name: Any = "") -> Any:
    if isinstance(name, str) and name:
        return _require_type(_find_object(ctx, name), "LIGHT")
    raise BridgeError(PRECONDITION, "light is required")


def _light_entry(obj: Any) -> dict:
    data = getattr(obj, "data", None)
    return {
        "light": getattr(obj, "name", ""),
        "type": getattr(data, "type", None),
        "location": _float_list(getattr(obj, "location", [])),
        "rotation": _float_list(getattr(obj, "rotation_euler", [])),
        "energy": float(getattr(data, "energy", 0.0) or 0.0),
        "color": _float_list(getattr(data, "color", [])),
        "size": float(getattr(data, "size", 0.0) or 0.0),
        "spot_size": float(getattr(data, "spot_size", 0.0) or 0.0),
        "spot_blend": float(getattr(data, "spot_blend", 0.0) or 0.0),
    }


def _set_light_data(obj: Any, payload: dict, *, defaults: bool = False) -> None:
    data = getattr(obj, "data", None)
    scalar_values = {
        "energy": float(payload.get("energy", 10.0)),
        "size": float(payload.get("size", getattr(data, "size", 1.0))),
        "spot_size": float(payload.get("spot_size", getattr(data, "spot_size", 0.785398))),
        "spot_blend": float(payload.get("spot_blend", getattr(data, "spot_blend", 0.15))),
    }
    for key, value in scalar_values.items():
        if defaults or key in payload:
            setattr(data, key, value)
    if defaults or "color" in payload:
        data.color = _vec(payload.get("color"), [1.0, 1.0, 1.0])


def light_create(ctx: Ctx, payload: dict) -> dict:
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    light_type = str(payload.get("type", "POINT"))
    location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    rotation = _vec(payload.get("rotation"), [0.0, 0.0, 0.0])
    ctx.bpy.ops.object.light_add(type=light_type, location=location, rotation=rotation)
    obj = _created(ctx, before, "LIGHT")
    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
    _set_light_data(obj, payload, defaults=True)
    return _light_entry(obj)


def light_list(ctx: Ctx, payload: dict) -> dict:
    lights = [_light_entry(obj) for obj in _scene_objects(ctx) if getattr(obj, "type", None) == "LIGHT"]
    return {"count": len(lights), "lights": lights}


def light_report(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("light", "")
    if isinstance(name, str) and name:
        return {"count": 1, "lights": [_light_entry(_resolve_light(ctx, name))]}
    return light_list(ctx, {})


def light_set(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_light(ctx, payload.get("light"))
    _set_light_data(obj, payload)
    return _light_entry(obj)


COMMANDS = [
    Command("camera.create", camera_create, mutates=True, feedback="viewport"),
    Command("camera.list", camera_list, mutates=False),
    Command("camera.report", camera_report, mutates=False),
    Command("camera.set", camera_set, mutates=True, feedback="viewport"),
    Command("camera.set_active", camera_set_active, mutates=True, feedback="viewport"),
    Command("light.create", light_create, mutates=True, feedback="viewport"),
    Command("light.list", light_list, mutates=False),
    Command("light.report", light_report, mutates=False),
    Command("light.set", light_set, mutates=True, feedback="viewport"),
]
