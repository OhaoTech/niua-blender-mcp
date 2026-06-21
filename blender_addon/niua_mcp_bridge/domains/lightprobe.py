"""Light probe GUI-parity handlers."""

from __future__ import annotations

import json
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, PRECONDITION, BridgeError

_LIGHTPROBE_TYPES = {"SPHERE", "PLANE", "VOLUME"}


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


def _lightprobe_objects(ctx: Ctx) -> list[Any]:
    return [obj for obj in _scene_objects(ctx) if getattr(obj, "type", None) == "LIGHT_PROBE"]


def _require_lightprobe(ctx: Ctx, name: Any) -> Any:
    obj = ctx.get_object(_require_name(name, "name"))
    if getattr(obj, "type", None) != "LIGHT_PROBE":
        raise BridgeError(
            PRECONDITION,
            f"object is not a light probe: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    if getattr(obj, "data", None) is None:
        raise BridgeError(PRECONDITION, f"light probe has no data: {getattr(obj, 'name', '?')}")
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


def _properties_report(owner: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prop in _iter_rna_props(owner):
        identifier = str(getattr(prop, "identifier", "") or "")
        if not identifier or identifier == "rna_type":
            continue
        entry: dict[str, Any] = {
            "name": str(getattr(prop, "name", "") or identifier),
            "description": str(getattr(prop, "description", "") or ""),
            "type": str(getattr(prop, "type", "") or ""),
            "subtype": str(getattr(prop, "subtype", "") or ""),
            "is_readonly": bool(getattr(prop, "is_readonly", False)),
            "is_array": bool(getattr(prop, "is_array", False)),
            "array_length": int(getattr(prop, "array_length", 0) or 0),
        }
        enum_items = _enum_items(prop)
        if enum_items:
            entry["enum_items"] = enum_items
        try:
            entry["value"] = _jsonable(getattr(owner, identifier))
            entry["readable"] = True
        except Exception as exc:  # noqa: BLE001 - some probe RNA can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _compact_probe(obj: Any) -> dict[str, Any]:
    data = getattr(obj, "data", None)
    return {
        "name": getattr(obj, "name", ""),
        "type": getattr(data, "type", None),
        "data": getattr(data, "name", None),
        "location": _float_list(getattr(obj, "location", [])),
        "influence_distance": getattr(data, "influence_distance", None),
        "clip_start": getattr(data, "clip_start", None),
        "intensity": getattr(data, "intensity", None),
    }


def _probe_report(obj: Any) -> dict[str, Any]:
    out = _compact_probe(obj)
    out["properties"] = _properties_report(obj.data)
    return out


def _object_report(obj: Any) -> dict[str, Any]:
    return {
        "object": getattr(obj, "name", ""),
        "type": getattr(obj, "type", ""),
        "location": _float_list(getattr(obj, "location", [])),
        "rotation": _float_list(getattr(obj, "rotation_euler", [])),
        "scale": _float_list(getattr(obj, "scale", [])),
        "lightprobe": _probe_report(obj),
    }


def _parse_json(raw: Any) -> Any:
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "value must be a JSON-encoded string")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise BridgeError(INVALID_PARAMS, f"value is not valid JSON: {exc}") from exc


def _coerce_value(ctx: Ctx, current: Any, value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("collection"), str):
        collection = getattr(getattr(ctx.bpy, "data", None), "collections", {}).get(value["collection"])
        if collection is None:
            raise BridgeError(INVALID_PARAMS, f"collection not found: {value['collection']}")
        return collection
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


def create(ctx: Ctx, payload: dict) -> dict:
    probe_type = str(payload.get("type", "")).upper()
    if probe_type not in _LIGHTPROBE_TYPES:
        raise BridgeError(INVALID_PARAMS, f"unsupported light probe type: {probe_type}")
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    ctx.bpy.ops.object.lightprobe_add(type=probe_type, location=_vec(payload.get("location"), [0.0, 0.0, 0.0]))
    obj = _created(ctx, before)
    if getattr(obj, "type", None) != "LIGHT_PROBE":
        raise BridgeError(PRECONDITION, f"created object is not a light probe: {getattr(obj, 'type', None)}")
    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
        data = getattr(obj, "data", None)
        if data is not None and hasattr(data, "name"):
            data.name = name
    return _object_report(obj)


def list_probes(ctx: Ctx, payload: dict) -> dict:
    probes = [_compact_probe(obj) for obj in _lightprobe_objects(ctx)]
    return {"lightprobe_count": len(probes), "lightprobes": probes}


def report(ctx: Ctx, payload: dict) -> dict:
    return _object_report(_require_lightprobe(ctx, payload.get("name")))


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj = _require_lightprobe(ctx, payload.get("name"))
    data = obj.data
    prop_name = _require_name(payload.get("property"), "property")
    if not hasattr(data, prop_name):
        raise BridgeError(INVALID_PARAMS, f"light probe property not found: {prop_name}")
    prop = _rna_prop(data, prop_name)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {prop_name}")
    value = _coerce_value(ctx, getattr(data, prop_name), _parse_json(payload.get("value")))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        try:
            setattr(data, prop_name, value)
        except (TypeError, ValueError, AttributeError) as exc:
            raise BridgeError(INVALID_PARAMS, f"could not set {prop_name}: {exc}") from exc
    return {
        "object": obj.name,
        "property": prop_name,
        "value": _jsonable(getattr(data, prop_name)),
        "lightprobe": _probe_report(obj),
    }


COMMANDS = [
    Command("lightprobe.create", create, mutates=True, feedback="viewport"),
    Command("lightprobe.list", list_probes, mutates=False),
    Command("lightprobe.report", report, mutates=False),
    Command("lightprobe.set", set_property, mutates=True, feedback="viewport"),
]
