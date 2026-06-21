"""Tool settings GUI-parity handlers."""

from __future__ import annotations

import json
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _area_type(payload: dict) -> str:
    return str(payload.get("area_type", "VIEW_3D") or "VIEW_3D").upper()


def _mode(ctx: Ctx, area_type: str, payload: dict) -> str:
    raw = payload.get("mode", "")
    if isinstance(raw, str) and raw:
        return raw.upper()
    bpy_ctx = getattr(ctx.bpy, "context", None)
    if area_type in {"VIEW_3D", "PROPERTIES"}:
        return str(getattr(bpy_ctx, "mode", "OBJECT") or "OBJECT")
    space_data = getattr(bpy_ctx, "space_data", None)
    if area_type == "IMAGE_EDITOR":
        return str(getattr(space_data, "mode", "VIEW") or "VIEW")
    if area_type == "SEQUENCE_EDITOR":
        return str(getattr(space_data, "view_type", "SEQUENCER") or "SEQUENCER")
    return "DEFAULT"


def _workspace(ctx: Ctx) -> Any:
    workspace = getattr(getattr(ctx.bpy, "context", None), "workspace", None)
    if workspace is None:
        raise BridgeError(PRECONDITION, "no active workspace")
    return workspace


def _tool_lookup(ctx: Ctx, area_type: str, mode: str, *, create: bool = False) -> Any:
    tools = getattr(_workspace(ctx), "tools", None)
    if tools is None:
        raise BridgeError(PRECONDITION, "workspace does not expose tools")
    try:
        if area_type in {"VIEW_3D", "PROPERTIES"}:
            return tools.from_space_view3d_mode(mode, create=create)
        if area_type == "IMAGE_EDITOR":
            return tools.from_space_image_mode(mode, create=create)
        if area_type == "NODE_EDITOR":
            return tools.from_space_node(create=create)
        if area_type == "SEQUENCE_EDITOR":
            return tools.from_space_sequencer(mode, create=create)
    except Exception as exc:  # noqa: BLE001 - Blender raises TypeError for unsupported mode enums
        raise BridgeError(INVALID_PARAMS, f"could not resolve tool for {area_type}/{mode}: {exc}") from exc
    raise BridgeError(INVALID_PARAMS, f"unsupported tool area type: {area_type}")


def _refresh_tool(tool: Any) -> str | None:
    refresh = getattr(tool, "refresh_from_context", None)
    if not callable(refresh):
        return None
    try:
        refresh()
    except Exception as exc:  # noqa: BLE001 - report, but do not fail active-tool reads
        return str(exc)
    return None


def _tool_summary(tool: Any | None) -> dict[str, Any] | None:
    if tool is None:
        return None
    refresh_error = _refresh_tool(tool)
    out = {
        "idname": str(getattr(tool, "idname", "") or ""),
        "idname_fallback": str(getattr(tool, "idname_fallback", "") or ""),
        "index": int(getattr(tool, "index", 0) or 0),
        "space_type": str(getattr(tool, "space_type", "") or ""),
        "mode": str(getattr(tool, "mode", "") or ""),
        "has_datablock": bool(getattr(tool, "has_datablock", False)),
        "use_brushes": bool(getattr(tool, "use_brushes", False)),
        "brush_type": str(getattr(tool, "brush_type", "") or ""),
        "widget": str(getattr(tool, "widget", "") or ""),
    }
    if refresh_error:
        out["refresh_error"] = refresh_error
    out["properties"] = _properties_report(tool)
    return out


def _active_payload(ctx: Ctx, payload: dict, *, create: bool = False) -> dict[str, Any]:
    area = _area_type(payload)
    mode = _mode(ctx, area, payload)
    tool = _tool_lookup(ctx, area, mode, create=create)
    summary = _tool_summary(tool)
    available = bool(summary and summary.get("idname"))
    return {
        "available": available,
        "reason": None if available else f"active tool not found for {area}/{mode}",
        "workspace": str(getattr(_workspace(ctx), "name", "") or ""),
        "area_type": area,
        "mode": mode,
        "active_tool": summary,
    }


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
        except Exception as exc:  # noqa: BLE001 - some tool setting RNA can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _tool_settings(ctx: Ctx) -> Any:
    settings = getattr(getattr(ctx.bpy, "context", None), "tool_settings", None)
    if settings is None:
        raise BridgeError(PRECONDITION, "context has no tool_settings")
    return settings


def _resolve_setting(ctx: Ctx, path: Any) -> tuple[Any, str]:
    setting_path = _require_name(path, "path")
    owner = _tool_settings(ctx)
    parts = setting_path.split(".")
    for part in parts[:-1]:
        if not hasattr(owner, part):
            raise BridgeError(NOT_FOUND, f"tool setting path not found: {setting_path}")
        owner = getattr(owner, part)
    attr = parts[-1]
    if not hasattr(owner, attr):
        raise BridgeError(NOT_FOUND, f"tool setting path not found: {setting_path}")
    return owner, attr


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


def active(ctx: Ctx, payload: dict) -> dict:
    return _active_payload(ctx, payload)


def set_tool(ctx: Ctx, payload: dict) -> dict:
    idname = _require_name(payload.get("idname"), "idname")
    area = _area_type(payload)
    mode = _mode(ctx, area, payload)
    with ctx.ensure(mode=mode if area in {"VIEW_3D", "PROPERTIES"} else None, area=area):
        op = ctx.bpy.ops.wm.tool_set_by_id
        ctx.check_poll(op)
        result = op(name=idname, space_type=area)
    result_names = _op_result_names(result)
    if "FINISHED" not in result_names:
        raise BridgeError(PRECONDITION, f"tool was not set: {idname}", {"operator_result": sorted(result_names)})
    return {
        "available": True,
        "applied": ["wm.tool_set_by_id"],
        "requested": {"idname": idname, "area_type": area, "mode": mode},
        **_active_payload(ctx, {"area_type": area, "mode": mode}, create=True),
    }


def settings(ctx: Ctx, payload: dict) -> dict:
    return {
        **_active_payload(ctx, payload),
        "tool_settings": {
            "type": str(getattr(getattr(_tool_settings(ctx), "bl_rna", None), "identifier", "") or type(_tool_settings(ctx)).__name__),
            "properties": _properties_report(_tool_settings(ctx)),
        },
    }


def setting_get(ctx: Ctx, payload: dict) -> dict:
    owner, attr = _resolve_setting(ctx, payload.get("path"))
    return {"path": payload.get("path"), "value": _jsonable(getattr(owner, attr))}


def setting_set(ctx: Ctx, payload: dict) -> dict:
    owner, attr = _resolve_setting(ctx, payload.get("path"))
    prop = _rna_prop(owner, attr)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {payload.get('path')}")
    value = _coerce_value(getattr(owner, attr), _parse_json(payload.get("value")))
    try:
        setattr(owner, attr, value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise BridgeError(INVALID_PARAMS, f"could not set {payload.get('path')}: {exc}") from exc
    return {"path": payload.get("path"), "value": _jsonable(getattr(owner, attr))}


COMMANDS = [
    Command("tool.active", active, mutates=False),
    Command("tool.set", set_tool, mutates=True, feedback="viewport"),
    Command("tool.settings", settings, mutates=False),
    Command("tool.setting_get", setting_get, mutates=False),
    Command("tool.setting_set", setting_set, mutates=True, feedback="viewport"),
]
