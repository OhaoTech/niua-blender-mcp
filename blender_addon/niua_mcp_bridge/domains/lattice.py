"""Lattice GUI-parity handlers."""

from __future__ import annotations

import json
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

_POINT_REPORT_LIMIT = 256


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _vec(value: Any, default: list[float] | None = None) -> list[float]:
    if value is None:
        if default is not None:
            return list(default)
        raise BridgeError(INVALID_PARAMS, "expected a 3-item array")
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise BridgeError(INVALID_PARAMS, "expected a 3-item array")
    return [float(item) for item in value]


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in value]
    except TypeError:
        return []


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


def _require_lattice(ctx: Ctx, name: Any) -> Any:
    obj = ctx.get_object(_require_name(name, "object"))
    if getattr(obj, "type", None) != "LATTICE":
        raise BridgeError(
            PRECONDITION,
            f"object is not a lattice: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    if getattr(obj, "data", None) is None:
        raise BridgeError(PRECONDITION, f"lattice has no data: {getattr(obj, 'name', '?')}")
    return obj


def _iter_rna_props(owner: Any) -> list[Any]:
    return list(getattr(getattr(owner, "bl_rna", None), "properties", []) or [])


def _rna_prop(owner: Any, identifier: str) -> Any | None:
    properties = getattr(getattr(owner, "bl_rna", None), "properties", None)
    if properties is not None:
        try:
            return properties[identifier]
        except (KeyError, TypeError, AttributeError):
            getter = getattr(properties, "get", None)
            prop = getter(identifier) if callable(getter) else None
            if prop is not None:
                return prop
    for prop in _iter_rna_props(owner):
        if getattr(prop, "identifier", "") == identifier:
            return prop
    return None


def _enum_items(prop: Any) -> list[dict[str, str]]:
    items = list(getattr(prop, "enum_items", []) or [])
    if not items:
        items = list(getattr(prop, "enum_items_static", []) or [])
    return [
        {"identifier": str(getattr(item, "identifier", "")), "name": str(getattr(item, "name", ""))}
        for item in items
        if getattr(item, "identifier", "")
    ]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    name = getattr(value, "name", None)
    if name is not None or getattr(value, "bl_rna", None) is not None:
        out = {"name": str(name)} if name is not None else {"repr": repr(value)}
        value_type = getattr(value, "type", None)
        if value_type is not None:
            out["type"] = str(value_type)
        return out
    try:
        return [_jsonable(item) for item in value]
    except Exception:  # noqa: BLE001 - arbitrary RNA values may expose partial sequence APIs
        return repr(value)


def _collection_value(value: Any) -> dict[str, Any]:
    try:
        items = list(value or [])
    except TypeError:
        return {"repr": repr(value)}
    sample = []
    for item in items[:20]:
        name = getattr(item, "name", None)
        sample.append(str(name) if name is not None else repr(item))
    return {"count": len(items), "items": sample, "truncated": len(items) > 20}


def _properties_report(owner: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prop in _iter_rna_props(owner):
        identifier = str(getattr(prop, "identifier", "") or "")
        if not identifier or identifier == "rna_type":
            continue
        prop_type = str(getattr(prop, "type", "") or "")
        entry: dict[str, Any] = {
            "name": str(getattr(prop, "name", "") or identifier),
            "description": str(getattr(prop, "description", "") or ""),
            "type": prop_type,
            "subtype": str(getattr(prop, "subtype", "") or ""),
            "is_readonly": bool(getattr(prop, "is_readonly", False)),
            "is_array": bool(getattr(prop, "is_array", False)),
            "array_length": int(getattr(prop, "array_length", 0) or 0),
        }
        enum_items = _enum_items(prop)
        if enum_items:
            entry["enum_items"] = enum_items
        try:
            value = getattr(owner, identifier)
            entry["value"] = _collection_value(value) if prop_type == "COLLECTION" else _jsonable(value)
            entry["readable"] = True
        except Exception as exc:  # noqa: BLE001 - some lattice RNA can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _point_report(point: Any, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "select": bool(getattr(point, "select", False)),
        "co": _float_list(getattr(point, "co", [])),
        "co_deform": _float_list(getattr(point, "co_deform", [])),
        "weight_softbody": float(getattr(point, "weight_softbody", 0.0) or 0.0),
        "properties": _properties_report(point),
    }


def _lattice_summary(obj: Any) -> dict[str, Any]:
    data = obj.data
    points = list(getattr(data, "points", []) or [])
    return {
        "data": getattr(data, "name", ""),
        "points_u": int(getattr(data, "points_u", 0) or 0),
        "points_v": int(getattr(data, "points_v", 0) or 0),
        "points_w": int(getattr(data, "points_w", 0) or 0),
        "interpolation_type_u": getattr(data, "interpolation_type_u", None),
        "interpolation_type_v": getattr(data, "interpolation_type_v", None),
        "interpolation_type_w": getattr(data, "interpolation_type_w", None),
        "use_outside": bool(getattr(data, "use_outside", False)),
        "point_count": len(points),
        "points": [_point_report(point, index) for index, point in enumerate(points[:_POINT_REPORT_LIMIT])],
        "points_truncated": len(points) > _POINT_REPORT_LIMIT,
        "properties": _properties_report(data),
    }


def _object_report(obj: Any) -> dict[str, Any]:
    return {
        "object": getattr(obj, "name", ""),
        "type": getattr(obj, "type", ""),
        "location": _float_list(getattr(obj, "location", [])),
        "rotation": _float_list(getattr(obj, "rotation_euler", [])),
        "scale": _float_list(getattr(obj, "scale", [])),
        "lattice": _lattice_summary(obj),
    }


def _parse_json(raw: Any) -> Any:
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "value must be a JSON-encoded string")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise BridgeError(INVALID_PARAMS, f"value is not valid JSON: {exc}") from exc


def _coerce_value(current: Any, value: Any) -> Any:
    if isinstance(current, bool):
        if isinstance(value, str):
            low = value.strip().lower()
            if low in {"true", "1", "yes", "on"}:
                return True
            if low in {"false", "0", "no", "off"}:
                return False
            raise BridgeError(INVALID_PARAMS, f"expected boolean value, got: {value!r}")
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value) if not isinstance(value, (list, tuple)) else value
    if isinstance(current, float):
        return float(value) if not isinstance(value, (list, tuple)) else value
    return value


def _op_result_names(result: Any) -> set[str]:
    try:
        return {str(item) for item in result}
    except Exception:  # noqa: BLE001
        return {str(result)}


def create(ctx: Ctx, payload: dict) -> dict:
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    ctx.bpy.ops.object.add(type="LATTICE", location=_vec(payload.get("location"), [0.0, 0.0, 0.0]))
    obj = _created(ctx, before)
    if getattr(obj, "type", None) != "LATTICE":
        raise BridgeError(PRECONDITION, f"created object is not a lattice: {getattr(obj, 'type', None)}")
    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
    return _object_report(obj)


def report(ctx: Ctx, payload: dict) -> dict:
    return _object_report(_require_lattice(ctx, payload.get("object")))


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj = _require_lattice(ctx, payload.get("object"))
    data = obj.data
    prop_name = _require_name(payload.get("property"), "property")
    if not hasattr(data, prop_name):
        raise BridgeError(INVALID_PARAMS, f"lattice property not found: {prop_name}")
    prop = _rna_prop(data, prop_name)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {prop_name}")
    value = _coerce_value(getattr(data, prop_name), _parse_json(payload.get("value")))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        try:
            setattr(data, prop_name, value)
        except (TypeError, ValueError, AttributeError) as exc:
            raise BridgeError(INVALID_PARAMS, f"could not set {prop_name}: {exc}") from exc
    return {
        "object": obj.name,
        "property": prop_name,
        "value": _jsonable(getattr(data, prop_name)),
        "lattice": _lattice_summary(obj),
    }


def point_set(ctx: Ctx, payload: dict) -> dict:
    obj = _require_lattice(ctx, payload.get("object"))
    points = list(getattr(obj.data, "points", []) or [])
    index = int(payload.get("index", -1))
    if index < 0 or index >= len(points):
        raise BridgeError(PRECONDITION, f"lattice point index out of range: {index}", {"point_count": len(points)})
    co_deform = _vec(payload.get("co_deform"))
    point = points[index]
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        try:
            point.co_deform = co_deform
        except (TypeError, ValueError, AttributeError) as exc:
            raise BridgeError(INVALID_PARAMS, f"could not set point {index}: {exc}") from exc
    return {"object": obj.name, "point": _point_report(point, index)}


# NOTE: there is deliberately no `lattice.convert_to_mesh`. Blender cannot do it: on a
# lattice, `bpy.ops.object.convert(target='MESH')` returns FINISHED and leaves the object
# a LATTICE, and `to_mesh()` raises "Object does not have geometry data" -- verified live
# on an operator-created 8-point lattice (docs/reports/tool-audit-2026-07-26.md). The tool
# existed and could never succeed, so it was removed rather than left to fail politely.
# A lattice is a deformer cage, not geometry; to get a mesh, convert what it deforms.

COMMANDS = [
    Command("lattice.create", create, mutates=True, feedback="viewport"),
    Command("lattice.report", report, mutates=False),
    Command("lattice.set", set_property, mutates=True, feedback="viewport"),
    Command("lattice.point_set", point_set, mutates=True, feedback="viewport"),
]
