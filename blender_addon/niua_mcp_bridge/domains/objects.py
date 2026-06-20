"""Object domain handlers: lifecycle, transforms, origins, and bounds."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command


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


def transform_get(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    return _object_state(obj)


def bounds(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    return _bounds_state(obj)


COMMANDS = [
    Command("object.transform_get", transform_get, mutates=False),
    Command("object.bounds", bounds, mutates=False),
]
