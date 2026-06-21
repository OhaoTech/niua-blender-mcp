"""Volume GUI-parity handlers."""

from __future__ import annotations

import json
import os
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _require_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(INVALID_PARAMS, "path is required")
    path = os.path.abspath(os.path.expanduser(value))
    if not os.path.exists(path):
        raise BridgeError(INVALID_PARAMS, f"path does not exist: {value}")
    return path


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


def _volume_objects(ctx: Ctx) -> list[Any]:
    return [obj for obj in _scene_objects(ctx) if getattr(obj, "type", None) == "VOLUME"]


def _volume_data_blocks(ctx: Ctx) -> list[Any]:
    volumes = getattr(getattr(ctx.bpy, "data", None), "volumes", [])
    return list(volumes or [])


def _resolve_volume(ctx: Ctx, name_or_object: Any) -> tuple[Any | None, Any]:
    name = _require_name(name_or_object, "name_or_object")
    obj = getattr(ctx.bpy.data.objects, "get", lambda _name: None)(name)
    if obj is not None:
        if getattr(obj, "type", None) != "VOLUME":
            raise BridgeError(
                PRECONDITION,
                f"object is not a volume: {getattr(obj, 'name', '?')}",
                {"type": getattr(obj, "type", None)},
            )
        data = getattr(obj, "data", None)
        if data is None:
            raise BridgeError(PRECONDITION, f"volume object has no data: {getattr(obj, 'name', '?')}")
        return obj, data

    data = getattr(ctx.bpy.data.volumes, "get", lambda _name: None)(name)
    if data is None:
        raise BridgeError(NOT_FOUND, f"volume not found: {name}")
    linked = next(
        (
            candidate
            for candidate in _volume_objects(ctx)
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
        except Exception as exc:  # noqa: BLE001 - some RNA reads can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _grid_report(grid: Any) -> dict[str, Any]:
    return {
        "name": getattr(grid, "name", ""),
        "data_type": str(getattr(grid, "data_type", "")),
        "channels": int(getattr(grid, "channels", 0) or 0),
        "matrix_object": _jsonable(getattr(grid, "matrix_object", [])),
        "is_loaded": bool(getattr(grid, "is_loaded", False)),
        "properties": _properties_report(grid),
    }


def _grids_report(data: Any) -> dict[str, Any]:
    grids_owner = getattr(data, "grids", [])
    load = getattr(grids_owner, "load", None)
    load_success = None
    load_error = None
    if callable(load):
        try:
            load_success = bool(load())
        except Exception as exc:  # noqa: BLE001 - invalid volume paths surface here
            load_success = False
            load_error = str(exc)
    grids = list(grids_owner or [])
    out = {
        "grid_count": len(grids),
        "grids": [_grid_report(grid) for grid in grids],
        "active_index": getattr(grids_owner, "active_index", None),
        "is_loaded": bool(getattr(grids_owner, "is_loaded", False)),
        "error_message": getattr(grids_owner, "error_message", ""),
        "frame": getattr(grids_owner, "frame", None),
        "frame_filepath": getattr(grids_owner, "frame_filepath", ""),
        "properties": _properties_report(grids_owner),
    }
    if load_success is not None:
        out["load_success"] = load_success
    if load_error:
        out["load_error"] = load_error
    return out


def _settings_report(owner: Any) -> dict[str, Any]:
    return {"properties": _properties_report(owner)}


def _volume_summary(obj: Any | None, data: Any) -> dict[str, Any]:
    return {
        "data": getattr(data, "name", ""),
        "filepath": getattr(data, "filepath", ""),
        "is_sequence": bool(getattr(data, "is_sequence", False)),
        "frame_start": int(getattr(data, "frame_start", 0) or 0),
        "frame_duration": int(getattr(data, "frame_duration", 0) or 0),
        "frame_offset": int(getattr(data, "frame_offset", 0) or 0),
        "sequence_mode": getattr(data, "sequence_mode", None),
        "material_count": len(list(getattr(data, "materials", []) or [])),
        "velocity_grid": getattr(data, "velocity_grid", ""),
        "velocity_unit": getattr(data, "velocity_unit", None),
        "velocity_scale": float(getattr(data, "velocity_scale", 0.0) or 0.0),
        "grids": _grids_report(data),
        "display": _settings_report(getattr(data, "display", None)),
        "render": _settings_report(getattr(data, "render", None)),
        "properties": _properties_report(data),
    }


def _object_report(obj: Any | None, data: Any) -> dict[str, Any]:
    return {
        "object": getattr(obj, "name", None),
        "type": getattr(obj, "type", "VOLUME" if obj is None else ""),
        "location": _float_list(getattr(obj, "location", [])) if obj is not None else None,
        "rotation": _float_list(getattr(obj, "rotation_euler", [])) if obj is not None else None,
        "scale": _float_list(getattr(obj, "scale", [])) if obj is not None else None,
        "volume": _volume_summary(obj, data),
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


def _resolve_property_owner(data: Any, property_path: Any) -> tuple[Any, str]:
    path = _require_name(property_path, "property")
    parts = path.split(".")
    if any(not part for part in parts):
        raise BridgeError(INVALID_PARAMS, f"invalid property path: {path}")
    owner = data
    for part in parts[:-1]:
        if not hasattr(owner, part):
            raise BridgeError(INVALID_PARAMS, f"volume property owner not found: {path}")
        owner = getattr(owner, part)
        if owner is None:
            raise BridgeError(INVALID_PARAMS, f"volume property owner is null: {part}")
    return owner, parts[-1]


def _op_result_names(result: Any) -> set[str]:
    try:
        return {str(item) for item in result}
    except Exception:  # noqa: BLE001
        return {str(result)}


def _rename_volume(obj: Any, name: Any) -> None:
    if isinstance(name, str) and name:
        obj.name = name
        if getattr(obj, "data", None) is not None and hasattr(obj.data, "name"):
            obj.data.name = name


def create_empty(ctx: Ctx, payload: dict) -> dict:
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    ctx.bpy.ops.object.volume_add(location=_vec(payload.get("location"), [0.0, 0.0, 0.0]))
    obj = _created(ctx, before)
    if getattr(obj, "type", None) != "VOLUME":
        raise BridgeError(PRECONDITION, f"created object is not a volume: {getattr(obj, 'type', None)}")
    _rename_volume(obj, payload.get("name"))
    return _object_report(obj, obj.data)


def import_volume(ctx: Ctx, payload: dict) -> dict:
    path = _require_path(payload.get("path"))
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    result = ctx.bpy.ops.object.volume_import(filepath=path)
    if "FINISHED" not in _op_result_names(result):
        raise BridgeError(PRECONDITION, f"volume import failed: {path}", {"operator_result": list(_op_result_names(result))})
    obj = _created(ctx, before)
    if getattr(obj, "type", None) != "VOLUME":
        raise BridgeError(PRECONDITION, f"imported object is not a volume: {getattr(obj, 'type', None)}")
    _rename_volume(obj, payload.get("name"))
    return _object_report(obj, obj.data)


def list_volumes(ctx: Ctx, payload: dict) -> dict:
    objects = _volume_objects(ctx)
    data_blocks = _volume_data_blocks(ctx)
    linked_data = {id(getattr(obj, "data", None)) for obj in objects}
    return {
        "volume_count": len(objects),
        "volumes": [
            {
                "name": getattr(obj, "name", ""),
                "data": getattr(getattr(obj, "data", None), "name", None),
                "filepath": getattr(getattr(obj, "data", None), "filepath", ""),
                "grid_count": len(list(getattr(getattr(obj, "data", None), "grids", []) or [])),
                "location": _float_list(getattr(obj, "location", [])),
            }
            for obj in objects
        ],
        "data_count": len(data_blocks),
        "orphan_data": [
            {
                "data": getattr(data, "name", ""),
                "filepath": getattr(data, "filepath", ""),
                "grid_count": len(list(getattr(data, "grids", []) or [])),
            }
            for data in data_blocks
            if id(data) not in linked_data
        ],
    }


def report(ctx: Ctx, payload: dict) -> dict:
    obj, data = _resolve_volume(ctx, payload.get("name_or_object"))
    return _object_report(obj, data)


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj, data = _resolve_volume(ctx, payload.get("name_or_object"))
    owner, prop_name = _resolve_property_owner(data, payload.get("property"))
    if not hasattr(owner, prop_name):
        raise BridgeError(INVALID_PARAMS, f"volume property not found: {payload.get('property')}")
    prop = _rna_prop(owner, prop_name)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {payload.get('property')}")
    value = _coerce_value(getattr(owner, prop_name), _parse_json(payload.get("value")))
    try:
        if obj is None:
            setattr(owner, prop_name, value)
        else:
            with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
                setattr(owner, prop_name, value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise BridgeError(INVALID_PARAMS, f"could not set {payload.get('property')}: {exc}") from exc
    return {
        "object": getattr(obj, "name", None),
        "volume": getattr(data, "name", ""),
        "property": payload.get("property"),
        "value": _jsonable(getattr(owner, prop_name)),
        "report": _object_report(obj, data),
    }


COMMANDS = [
    Command("volume.create_empty", create_empty, mutates=True, feedback="viewport"),
    Command("volume.import", import_volume, mutates=True, feedback="viewport"),
    Command("volume.list", list_volumes, mutates=False),
    Command("volume.report", report, mutates=False),
    Command("volume.set", set_property, mutates=True, feedback="viewport"),
]
