"""Object domain handlers: lifecycle, transforms, origins, and bounds."""

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
    "TORUS": ("mesh", "primitive_torus_add"),
    "MONKEY": ("mesh", "primitive_monkey_add"),
    "EMPTY": ("object", "empty_add"),
}


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in value]
    except TypeError:
        return []


def _matrix_rows(matrix: Any) -> list[list[float]]:
    if matrix is None:
        return []
    try:
        return [[float(value) for value in row] for row in matrix]
    except TypeError:
        return []


def _collection_names(obj: Any) -> list[str]:
    return [getattr(collection, "name", "") for collection in getattr(obj, "users_collection", []) or []]


def _vec(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise BridgeError(INVALID_PARAMS, "expected a 3-item array")
    return [float(item) for item in value]


def _object_state(obj: Any) -> dict:
    parent = getattr(obj, "parent", None)
    return {
        "name": getattr(obj, "name", ""),
        "type": getattr(obj, "type", ""),
        "location": _float_list(getattr(obj, "location", [])),
        "rotation": _float_list(getattr(obj, "rotation_euler", [])),
        "scale": _float_list(getattr(obj, "scale", [])),
        "delta_location": _float_list(getattr(obj, "delta_location", [])),
        "delta_rotation": _float_list(getattr(obj, "delta_rotation_euler", [])),
        "delta_scale": _float_list(getattr(obj, "delta_scale", [])),
        "rotation_mode": getattr(obj, "rotation_mode", ""),
        "dimensions": _float_list(getattr(obj, "dimensions", [])),
        "parent": getattr(parent, "name", None) if parent is not None else None,
        "collections": _collection_names(obj),
        "matrix_world": _matrix_rows(getattr(obj, "matrix_world", None)),
    }


def _world_point(matrix: Any, corner: Any) -> list[float]:
    if matrix is None:
        return _float_list(corner)
    try:
        from mathutils import Vector  # noqa: PLC0415 - Blender-only import

        return _float_list(matrix @ Vector(corner))
    except Exception:  # noqa: BLE001 - fake bpy and partial objects use simpler matrices
        try:
            return _float_list(matrix @ corner)
        except Exception:  # noqa: BLE001
            return _float_list(corner)


def _center(corners: list[list[float]]) -> list[float]:
    if not corners:
        return []
    return [sum(corner[i] for corner in corners) / len(corners) for i in range(3)]


def _bounds_state(obj: Any) -> dict:
    local = [_float_list(corner) for corner in (getattr(obj, "bound_box", []) or [])]
    matrix = getattr(obj, "matrix_world", None)
    world = [_world_point(matrix, corner) for corner in local]
    return {
        "object": getattr(obj, "name", ""),
        "dimensions": _float_list(getattr(obj, "dimensions", [])),
        "local": local,
        "world": world,
        "center": _center(world),
    }


def _scene_objects(ctx: Ctx) -> list[Any]:
    return list(getattr(ctx.bpy.context.scene, "objects", []) or [])


def _created(ctx: Ctx, before: set[str]) -> Any:
    obj = getattr(ctx.bpy.context, "object", None)
    if obj is not None and getattr(obj, "name", "") not in before:
        return obj
    for candidate in reversed(_scene_objects(ctx)):
        if getattr(candidate, "name", "") not in before:
            return candidate
    raise BridgeError(HANDLER_ERROR, "no object was created")


def _create_kwargs(otype: str, payload: dict) -> dict:
    location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    rotation = _vec(payload.get("rotation"), [0.0, 0.0, 0.0])
    scale = _vec(payload.get("scale"), [1.0, 1.0, 1.0])
    calc_uvs = bool(payload.get("calc_uvs", True))

    if otype in {"CUBE", "PLANE", "MONKEY"}:
        return {
            "size": float(payload.get("size", 2.0)),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "SPHERE":
        return {
            "segments": int(payload.get("vertices", 32)),
            "radius": float(payload.get("radius", 1.0)),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "CYLINDER":
        return {
            "vertices": int(payload.get("vertices", 32)),
            "radius": float(payload.get("radius", 1.0)),
            "depth": float(payload.get("depth", 2.0)),
            "end_fill_type": str(payload.get("end_fill_type", "NGON")),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "CONE":
        return {
            "vertices": int(payload.get("vertices", 32)),
            "radius1": float(payload.get("radius1", 1.0)),
            "radius2": float(payload.get("radius2", 0.0)),
            "depth": float(payload.get("depth", 2.0)),
            "end_fill_type": str(payload.get("end_fill_type", "NGON")),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "TORUS":
        return {
            "major_radius": float(payload.get("major_radius", 1.0)),
            "minor_radius": float(payload.get("minor_radius", 0.25)),
            "major_segments": int(payload.get("major_segments", 48)),
            "minor_segments": int(payload.get("minor_segments", 12)),
            "location": location,
            "rotation": rotation,
        }
    if otype == "EMPTY":
        return {
            "type": str(payload.get("empty_display_type", "PLAIN_AXES")),
            "radius": float(payload.get("radius", 1.0)),
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    raise BridgeError(INVALID_PARAMS, f"unsupported object type: {otype}")


def create_object(ctx: Ctx, payload: dict) -> dict:
    otype = str(payload.get("type", "")).upper()
    if otype not in _PRIMITIVES:
        raise BridgeError(INVALID_PARAMS, f"unsupported object type: {otype}")

    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    group, op_name = _PRIMITIVES[otype]
    getattr(getattr(ctx.bpy.ops, group), op_name)(**_create_kwargs(otype, payload))
    obj = _created(ctx, before)

    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
    if otype == "TORUS":
        obj.scale = _vec(payload.get("scale"), [1.0, 1.0, 1.0])
    return _object_state(obj)


def transform_get(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    return _object_state(obj)


def bounds(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    return _bounds_state(obj)


COMMANDS = [
    Command("object.create", create_object, mutates=True, feedback="viewport"),
    Command("object.transform_get", transform_get, mutates=False),
    Command("object.bounds", bounds, mutates=False),
]
