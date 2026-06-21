"""Point cloud GUI-parity handlers."""

from __future__ import annotations

import json
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

_POINT_REPORT_LIMIT = 64
_ATTRIBUTE_SAMPLE_LIMIT = 8


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in value]
    except TypeError:
        return []


def _scene_objects(ctx: Ctx) -> list[Any]:
    return list(getattr(ctx.bpy.context.scene, "objects", []) or [])


def _pointcloud_objects(ctx: Ctx) -> list[Any]:
    return [
        obj
        for obj in _scene_objects(ctx)
        if getattr(obj, "type", None) == "POINTCLOUD" and getattr(obj, "data", None) is not None
    ]


def _pointcloud_data_blocks(ctx: Ctx) -> list[Any]:
    pointclouds = getattr(getattr(ctx.bpy, "data", None), "pointclouds", [])
    return list(pointclouds or [])


def _resolve_pointcloud(ctx: Ctx, name_or_object: Any) -> tuple[Any | None, Any]:
    name = _require_name(name_or_object, "name_or_object")
    obj = getattr(ctx.bpy.data.objects, "get", lambda _name: None)(name)
    if obj is not None:
        if getattr(obj, "type", None) != "POINTCLOUD":
            raise BridgeError(
                PRECONDITION,
                f"object is not a point cloud: {getattr(obj, 'name', '?')}",
                {"type": getattr(obj, "type", None)},
            )
        data = getattr(obj, "data", None)
        if data is None:
            raise BridgeError(PRECONDITION, f"point cloud object has no data: {getattr(obj, 'name', '?')}")
        return obj, data

    data = getattr(ctx.bpy.data.pointclouds, "get", lambda _name: None)(name)
    if data is None:
        raise BridgeError(NOT_FOUND, f"point cloud not found: {name}")
    linked = next(
        (
            candidate
            for candidate in _pointcloud_objects(ctx)
            if getattr(candidate, "data", None) is data or getattr(getattr(candidate, "data", None), "name", None) == name
        ),
        None,
    )
    return linked, data


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
    for index, item in enumerate(items[:20]):
        name = getattr(item, "name", None)
        if name is not None:
            sample.append(str(name))
        elif hasattr(item, "index"):
            sample.append({"index": int(getattr(item, "index", index))})
        else:
            sample.append(repr(item))
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
        except Exception as exc:  # noqa: BLE001 - some RNA reads can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _point_report(point: Any, fallback_index: int) -> dict[str, Any]:
    return {
        "index": int(getattr(point, "index", fallback_index)),
        "co": _float_list(getattr(point, "co", [])),
        "radius": float(getattr(point, "radius", 0.0) or 0.0),
    }


def _attribute_value(item: Any) -> Any:
    for field in ("value", "vector", "color", "color_srgb", "byte_color"):
        if hasattr(item, field):
            return _jsonable(getattr(item, field))
    return _jsonable(item)


def _attribute_report(attribute: Any) -> dict[str, Any]:
    data = list(getattr(attribute, "data", []) or [])
    return {
        "name": str(getattr(attribute, "name", "")),
        "data_type": str(getattr(attribute, "data_type", "")),
        "domain": str(getattr(attribute, "domain", "")),
        "count": len(data),
        "sample": [_attribute_value(item) for item in data[:_ATTRIBUTE_SAMPLE_LIMIT]],
        "truncated": len(data) > _ATTRIBUTE_SAMPLE_LIMIT,
    }


def _attributes_payload(obj: Any | None, data: Any) -> dict[str, Any]:
    attributes = [_attribute_report(attribute) for attribute in list(getattr(data, "attributes", []) or [])]
    color_attributes = [
        _attribute_report(attribute) for attribute in list(getattr(data, "color_attributes", []) or [])
    ]
    return {
        "object": getattr(obj, "name", None),
        "pointcloud": getattr(data, "name", ""),
        "attribute_count": len(attributes),
        "attributes": attributes,
        "color_attribute_count": len(color_attributes),
        "color_attributes": color_attributes,
    }


def _pointcloud_summary(obj: Any | None, data: Any) -> dict[str, Any]:
    points = list(getattr(data, "points", []) or [])
    summary = _attributes_payload(obj, data)
    return {
        "data": getattr(data, "name", ""),
        "point_count": len(points),
        "material_count": len(list(getattr(data, "materials", []) or [])),
        "points": [_point_report(point, index) for index, point in enumerate(points[:_POINT_REPORT_LIMIT])],
        "points_truncated": len(points) > _POINT_REPORT_LIMIT,
        "attribute_count": summary["attribute_count"],
        "color_attribute_count": summary["color_attribute_count"],
        "properties": _properties_report(data),
    }


def _object_report(obj: Any | None, data: Any) -> dict[str, Any]:
    return {
        "object": getattr(obj, "name", None),
        "type": getattr(obj, "type", "POINTCLOUD" if obj is None else ""),
        "location": _float_list(getattr(obj, "location", [])) if obj is not None else None,
        "rotation": _float_list(getattr(obj, "rotation_euler", [])) if obj is not None else None,
        "scale": _float_list(getattr(obj, "scale", [])) if obj is not None else None,
        "pointcloud": _pointcloud_summary(obj, data),
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


def list_pointclouds(ctx: Ctx, payload: dict) -> dict:
    objects = _pointcloud_objects(ctx)
    data_blocks = _pointcloud_data_blocks(ctx)
    linked_data = {id(getattr(obj, "data", None)) for obj in objects}
    return {
        "pointcloud_count": len(objects),
        "pointclouds": [
            {
                "object": getattr(obj, "name", ""),
                "data": getattr(getattr(obj, "data", None), "name", None),
                "point_count": len(list(getattr(getattr(obj, "data", None), "points", []) or [])),
                "attribute_count": len(list(getattr(getattr(obj, "data", None), "attributes", []) or [])),
                "color_attribute_count": len(
                    list(getattr(getattr(obj, "data", None), "color_attributes", []) or [])
                ),
            }
            for obj in objects
        ],
        "data_count": len(data_blocks),
        "orphan_data": [
            {
                "data": getattr(data, "name", ""),
                "point_count": len(list(getattr(data, "points", []) or [])),
                "attribute_count": len(list(getattr(data, "attributes", []) or [])),
            }
            for data in data_blocks
            if id(data) not in linked_data
        ],
    }


def report(ctx: Ctx, payload: dict) -> dict:
    obj, data = _resolve_pointcloud(ctx, payload.get("name_or_object"))
    return _object_report(obj, data)


def attributes(ctx: Ctx, payload: dict) -> dict:
    obj, data = _resolve_pointcloud(ctx, payload.get("name_or_object"))
    return _attributes_payload(obj, data)


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj, data = _resolve_pointcloud(ctx, payload.get("name_or_object"))
    prop_name = _require_name(payload.get("property"), "property")
    if not hasattr(data, prop_name):
        raise BridgeError(INVALID_PARAMS, f"point cloud property not found: {prop_name}")
    prop = _rna_prop(data, prop_name)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {prop_name}")
    value = _coerce_value(getattr(data, prop_name), _parse_json(payload.get("value")))

    try:
        if obj is None:
            setattr(data, prop_name, value)
        else:
            with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
                setattr(data, prop_name, value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise BridgeError(INVALID_PARAMS, f"could not set {prop_name}: {exc}") from exc

    return {
        "object": getattr(obj, "name", None),
        "pointcloud": getattr(data, "name", ""),
        "property": prop_name,
        "value": _jsonable(getattr(data, prop_name)),
        "report": _object_report(obj, data),
    }


COMMANDS = [
    Command("pointcloud.list", list_pointclouds, mutates=False),
    Command("pointcloud.report", report, mutates=False),
    Command("pointcloud.set", set_property, mutates=True, feedback="viewport"),
    Command("pointcloud.attributes", attributes, mutates=False),
]
