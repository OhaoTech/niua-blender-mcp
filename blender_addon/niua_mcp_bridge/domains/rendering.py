"""Rendering subsystem handlers: cameras, lights, render settings, world, compositor."""

from __future__ import annotations

import os
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


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


def _render_settings(ctx: Ctx) -> dict:
    scene = ctx.bpy.context.scene
    render = scene.render
    image_settings = getattr(render, "image_settings", None)
    camera = getattr(scene, "camera", None)
    return {
        "scene": getattr(scene, "name", None),
        "engine": getattr(render, "engine", None),
        "filepath": getattr(render, "filepath", ""),
        "resolution": [int(getattr(render, "resolution_x", 0) or 0), int(getattr(render, "resolution_y", 0) or 0)],
        "resolution_percentage": int(getattr(render, "resolution_percentage", 0) or 0),
        "image_format": getattr(image_settings, "file_format", None),
        "transparent": bool(getattr(render, "film_transparent", False)),
        "camera": getattr(camera, "name", None) if camera is not None else None,
    }


def render_settings(ctx: Ctx, payload: dict) -> dict:
    return _render_settings(ctx)


def _apply_render_settings(ctx: Ctx, payload: dict) -> None:
    render = ctx.bpy.context.scene.render
    if payload.get("engine") is not None:
        render.engine = str(payload["engine"])
    if payload.get("filepath") is not None:
        render.filepath = str(payload["filepath"])
    if payload.get("resolution_x") is not None:
        render.resolution_x = int(payload["resolution_x"])
    if payload.get("resolution_y") is not None:
        render.resolution_y = int(payload["resolution_y"])
    if payload.get("transparent") is not None:
        render.film_transparent = bool(payload["transparent"])
    if payload.get("image_format") is not None:
        render.image_settings.file_format = str(payload["image_format"])


def render_set_settings(ctx: Ctx, payload: dict) -> dict:
    _apply_render_settings(ctx, payload)
    return _render_settings(ctx)


def render_still(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required")
    scene = ctx.bpy.context.scene
    render = scene.render
    image_settings = render.image_settings
    old = {
        "filepath": render.filepath,
        "engine": render.engine,
        "resolution_x": render.resolution_x,
        "resolution_y": render.resolution_y,
        "image_format": image_settings.file_format,
        "camera": getattr(scene, "camera", None),
    }
    try:
        render.filepath = path
        image_settings.file_format = str(payload.get("image_format", "PNG"))
        if payload.get("engine") is not None:
            render.engine = str(payload["engine"])
        if payload.get("resolution_x") is not None:
            render.resolution_x = int(payload["resolution_x"])
        if payload.get("resolution_y") is not None:
            render.resolution_y = int(payload["resolution_y"])
        if payload.get("camera"):
            scene.camera = _resolve_camera(ctx, payload.get("camera"))
        op = ctx.bpy.ops.render.render
        ctx.check_poll(op)
        try:
            op(write_still=True)
        except Exception as exc:  # noqa: BLE001 - Blender render operators raise runtime errors
            raise BridgeError(PRECONDITION, f"could not render still: {exc}", {"path": path}) from exc
    finally:
        render.filepath = old["filepath"]
        render.engine = old["engine"]
        render.resolution_x = old["resolution_x"]
        render.resolution_y = old["resolution_y"]
        image_settings.file_format = old["image_format"]
        scene.camera = old["camera"]
    return {
        "path": path,
        "format": str(payload.get("image_format", "PNG")),
        "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
    }


def _socket_get(sockets: Any, name: str) -> Any:
    getter = getattr(sockets, "get", None)
    if callable(getter):
        return getter(name)
    try:
        return sockets[name]
    except Exception:  # noqa: BLE001
        return None


def _background_node(world: Any) -> Any:
    tree = getattr(world, "node_tree", None)
    nodes = getattr(tree, "nodes", None)
    getter = getattr(nodes, "get", None)
    node = getter("Background") if callable(getter) else None
    if node is None:
        node = next((candidate for candidate in list(nodes or []) if getattr(candidate, "type", None) == "BACKGROUND"), None)
    return node


def _world_strength(world: Any) -> float | None:
    node = _background_node(world)
    if node is None:
        return None
    socket = _socket_get(getattr(node, "inputs", None), "Strength")
    value = getattr(socket, "default_value", None) if socket is not None else None
    return float(value) if value is not None else None


def world_report(ctx: Ctx, payload: dict) -> dict:
    world = getattr(ctx.bpy.context.scene, "world", None)
    if world is None:
        raise BridgeError(PRECONDITION, "scene has no world")
    return {
        "world": getattr(world, "name", None),
        "color": _float_list(getattr(world, "color", [])),
        "use_nodes": bool(getattr(world, "use_nodes", False)),
        "strength": _world_strength(world),
    }


def world_set(ctx: Ctx, payload: dict) -> dict:
    world = getattr(ctx.bpy.context.scene, "world", None)
    if world is None:
        raise BridgeError(PRECONDITION, "scene has no world")
    if payload.get("color") is not None:
        world.color = _vec(payload.get("color"), [0.05, 0.05, 0.05])
    if payload.get("strength") is not None:
        world.use_nodes = True
        node = _background_node(world)
        if node is None:
            raise BridgeError(PRECONDITION, "world has no Background node")
        socket = _socket_get(getattr(node, "inputs", None), "Strength")
        if socket is None:
            raise BridgeError(PRECONDITION, "world Background node has no Strength input")
        socket.default_value = float(payload["strength"])
    return world_report(ctx, {})


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
    Command("render.settings", render_settings, mutates=False),
    Command("render.set_settings", render_set_settings, mutates=True, feedback="viewport"),
    Command("render.still", render_still, mutates=False),
    Command("world.report", world_report, mutates=False),
    Command("world.set", world_set, mutates=True, feedback="viewport"),
]
