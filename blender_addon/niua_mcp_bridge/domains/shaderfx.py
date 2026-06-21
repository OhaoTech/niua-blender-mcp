"""Shader effects GUI-parity handlers."""

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


def _resolve_object(ctx: Ctx, payload: dict) -> Any:
    return ctx.get_object(_require_name(payload.get("object"), "object"))


def _effects_collection(obj: Any) -> Any:
    effects = getattr(obj, "shader_effects", None)
    if effects is None:
        raise BridgeError(
            PRECONDITION,
            f"object does not expose shader effects: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    return effects


def _effect_list(obj: Any) -> list[Any]:
    return list(_effects_collection(obj) or [])


def _get_effect(obj: Any, name: Any) -> Any:
    effect_name = _require_name(name, "shader effect name")
    effects = _effects_collection(obj)
    getter = getattr(effects, "get", None)
    effect = getter(effect_name) if callable(getter) else None
    if effect is None:
        effect = next((candidate for candidate in _effect_list(obj) if getattr(candidate, "name", None) == effect_name), None)
    if effect is None:
        raise BridgeError(NOT_FOUND, f"shader effect not found: {effect_name}", {"object": getattr(obj, "name", "?")})
    return effect


def _index_of(obj: Any, effect: Any) -> int:
    for index, candidate in enumerate(_effect_list(obj)):
        if candidate is effect or getattr(candidate, "name", None) == getattr(effect, "name", None):
            return index
    return -1


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
    if name is not None:
        out = {"name": str(name)}
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
        except Exception as exc:  # noqa: BLE001 - some shader effect RNA can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _compact_effect(obj: Any, effect: Any) -> dict[str, Any]:
    return {
        "index": _index_of(obj, effect),
        "name": getattr(effect, "name", ""),
        "type": getattr(effect, "type", None),
        "show_viewport": bool(getattr(effect, "show_viewport", True)),
        "show_render": bool(getattr(effect, "show_render", True)),
        "show_in_editmode": bool(getattr(effect, "show_in_editmode", False)),
        "show_expanded": bool(getattr(effect, "show_expanded", True)),
    }


def _effect_report(obj: Any, effect: Any) -> dict[str, Any]:
    out = _compact_effect(obj, effect)
    out["properties"] = _properties_report(effect)
    return out


def _list_payload(obj: Any) -> dict[str, Any]:
    effects = [_compact_effect(obj, effect) for effect in _effect_list(obj)]
    return {"object": obj.name, "shaderfx_count": len(effects), "shaderfx": effects}


def _report_payload(obj: Any, name: Any = "") -> dict[str, Any]:
    if isinstance(name, str) and name:
        return {"object": obj.name, "shaderfx": _effect_report(obj, _get_effect(obj, name))}
    effects = [_effect_report(obj, effect) for effect in _effect_list(obj)]
    return {"object": obj.name, "shaderfx_count": len(effects), "shaderfx": effects}


def _shaderfx_type_items(ctx: Ctx) -> list[Any]:
    shaderfx_type = getattr(getattr(ctx.bpy, "types", None), "ShaderFx", None)
    prop = _rna_prop(shaderfx_type, "type") if shaderfx_type is not None else None
    return list(getattr(prop, "enum_items", []) or getattr(prop, "enum_items_static", []) or [])


def _parse_json(raw: Any) -> Any:
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "value must be a JSON-encoded string")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise BridgeError(INVALID_PARAMS, f"value is not valid JSON: {exc}") from exc


def _coerce_value(ctx: Ctx, current: Any, value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("object"), str):
        return ctx.get_object(value["object"])
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


def _resolve_property(effect: Any, path: str) -> tuple[Any, str]:
    if not isinstance(path, str) or not path:
        raise BridgeError(PRECONDITION, "property is required")
    owner = effect
    attr = path
    if "." in path:
        parts = path.split(".")
        for part in parts[:-1]:
            if not hasattr(owner, part):
                raise BridgeError(INVALID_PARAMS, f"shader effect property path not found: {path}")
            owner = getattr(owner, part)
        attr = parts[-1]
    if not hasattr(owner, attr):
        raise BridgeError(INVALID_PARAMS, f"shader effect property not found: {path}")
    return owner, attr


def list_effects(ctx: Ctx, payload: dict) -> dict:
    return _list_payload(_resolve_object(ctx, payload))


def types_list(ctx: Ctx, payload: dict) -> dict:
    types = [
        {"identifier": str(getattr(item, "identifier", "")), "name": str(getattr(item, "name", ""))}
        for item in _shaderfx_type_items(ctx)
        if getattr(item, "identifier", "")
    ]
    return {"type_count": len(types), "types": types}


def add(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    _effects_collection(obj)
    effect_type = str(payload.get("type", "")).upper()
    if not effect_type:
        raise BridgeError(PRECONDITION, "type is required")
    before = set(id(effect) for effect in _effect_list(obj))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        op = ctx.bpy.ops.object.shaderfx_add
        ctx.check_poll(op)
        try:
            op(type=effect_type)
        except (TypeError, ValueError, RuntimeError) as exc:
            raise BridgeError(INVALID_PARAMS, f"could not add shader effect of type {effect_type}: {exc}") from exc
    created = next((effect for effect in reversed(_effect_list(obj)) if id(effect) not in before), None)
    if created is None and _effect_list(obj):
        created = _effect_list(obj)[-1]
    if created is None:
        raise BridgeError(PRECONDITION, "no shader effect was created")
    name = payload.get("name")
    if isinstance(name, str) and name:
        created.name = name
    return {"object": obj.name, "shaderfx": _effect_report(obj, created)}


def remove(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    effect = _get_effect(obj, payload.get("name"))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        op = ctx.bpy.ops.object.shaderfx_remove
        ctx.check_poll(op)
        op(shaderfx=getattr(effect, "name", ""))
    return _list_payload(obj)


def report(ctx: Ctx, payload: dict) -> dict:
    return _report_payload(_resolve_object(ctx, payload), payload.get("name", ""))


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    effect = _get_effect(obj, payload.get("name"))
    path = _require_name(payload.get("property"), "property")
    owner, attr = _resolve_property(effect, path)
    prop = _rna_prop(owner, attr)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {path}")
    value = _coerce_value(ctx, getattr(owner, attr), _parse_json(payload.get("value")))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        try:
            setattr(owner, attr, value)
        except (TypeError, ValueError, AttributeError) as exc:
            raise BridgeError(INVALID_PARAMS, f"could not set {path}: {exc}") from exc
    return {
        "object": obj.name,
        "name": getattr(effect, "name", ""),
        "property": path,
        "value": _jsonable(getattr(owner, attr)),
        "shaderfx": _effect_report(obj, effect),
    }


COMMANDS = [
    Command("shaderfx.list", list_effects, mutates=False),
    Command("shaderfx.types", types_list, mutates=False),
    Command("shaderfx.add", add, mutates=True, feedback="viewport"),
    Command("shaderfx.remove", remove, mutates=True, feedback="viewport"),
    Command("shaderfx.report", report, mutates=False),
    Command("shaderfx.set", set_property, mutates=True, feedback="viewport"),
]
