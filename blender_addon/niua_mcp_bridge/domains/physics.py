"""Physics GUI-parity handlers."""

from __future__ import annotations

import json
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

_TYPES = {"RIGID_BODY", "RIGID_BODY_CONSTRAINT", "CLOTH", "SOFT_BODY", "FLUID", "DYNAMIC_PAINT", "FIELD"}
_ATTR_TYPES = {
    "RIGID_BODY": "rigid_body",
    "RIGID_BODY_CONSTRAINT": "rigid_body_constraint",
}
_ORDERED_TYPES = ["RIGID_BODY", "RIGID_BODY_CONSTRAINT", "CLOTH", "SOFT_BODY", "FLUID", "DYNAMIC_PAINT", "FIELD"]


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _physics_type(value: Any) -> str:
    physics_type = str(value or "").upper()
    if physics_type not in _TYPES:
        raise BridgeError(INVALID_PARAMS, f"unsupported physics type: {physics_type}")
    return physics_type


def _resolve_object(ctx: Ctx, payload: dict) -> Any:
    return ctx.get_object(_require_name(payload.get("object"), "object"))


def _modifier_for_type(obj: Any, physics_type: str) -> Any | None:
    for mod in list(getattr(obj, "modifiers", []) or []):
        if getattr(mod, "type", None) == physics_type:
            return mod
    return None


def _field_enabled(field: Any) -> bool:
    return field is not None and getattr(field, "type", None) not in {None, "NONE"}


def _physics_owner(obj: Any, physics_type: str, *, required: bool = False) -> Any | None:
    if physics_type in _ATTR_TYPES:
        owner = getattr(obj, _ATTR_TYPES[physics_type], None)
    elif physics_type == "FIELD":
        field = getattr(obj, "field", None)
        owner = field if _field_enabled(field) else None
    else:
        owner = _modifier_for_type(obj, physics_type)
    if owner is None and required:
        raise BridgeError(NOT_FOUND, f"physics stack not found: {physics_type}", {"object": getattr(obj, "name", "?")})
    return owner


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


def _iter_rna_props(owner: Any) -> list[Any]:
    return list(getattr(getattr(owner, "bl_rna", None), "properties", []) or [])


def _rna_prop(owner: Any, identifier: str) -> Any | None:
    for prop in _iter_rna_props(owner):
        if getattr(prop, "identifier", "") == identifier:
            return prop
    return None


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
        enum_items = [
            {"identifier": str(getattr(item, "identifier", "")), "name": str(getattr(item, "name", ""))}
            for item in list(getattr(prop, "enum_items", []) or [])
            if getattr(item, "identifier", "")
        ]
        if enum_items:
            entry["enum_items"] = enum_items
        try:
            entry["value"] = _jsonable(getattr(owner, identifier))
            entry["readable"] = True
        except Exception as exc:  # noqa: BLE001 - some RNA properties can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _unit_report(owner: Any | None) -> dict[str, Any] | None:
    if owner is None:
        return None
    out: dict[str, Any] = {
        "name": getattr(owner, "name", None),
        "type": getattr(owner, "type", None),
        "properties": _properties_report(owner),
    }
    settings = getattr(owner, "settings", None)
    if settings is not None:
        out["settings"] = {"properties": _properties_report(settings)}
    return out


def _report(obj: Any) -> dict[str, Any]:
    physics = {
        physics_type: _unit_report(_physics_owner(obj, physics_type))
        for physics_type in _ORDERED_TYPES
    }
    present = [physics_type for physics_type, value in physics.items() if value is not None]
    return {"object": obj.name, "present": present, "physics": physics}


def _field_payload(obj: Any) -> dict[str, Any]:
    field = getattr(obj, "field", None)
    enabled = _field_enabled(field)
    return {"object": obj.name, "enabled": enabled, "field": _unit_report(field) if enabled else None}


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


def _resolve_property(owner: Any, path: str) -> tuple[Any, str]:
    if not isinstance(path, str) or not path:
        raise BridgeError(PRECONDITION, "property is required")
    current = owner
    parts = path.split(".")
    for part in parts[:-1]:
        if not hasattr(current, part):
            raise BridgeError(INVALID_PARAMS, f"physics property path not found: {path}")
        current = getattr(current, part)
    attr = parts[-1]
    if not hasattr(current, attr):
        raise BridgeError(INVALID_PARAMS, f"physics property not found: {path}")
    return current, attr


def _set_owner_property(ctx: Ctx, obj: Any, owner: Any, path: str, raw_value: Any) -> dict[str, Any]:
    target, attr = _resolve_property(owner, path)
    prop = _rna_prop(target, attr)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {path}")
    value = _coerce_value(ctx, getattr(target, attr), _parse_json(raw_value))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        try:
            setattr(target, attr, value)
        except (TypeError, ValueError, AttributeError) as exc:
            raise BridgeError(INVALID_PARAMS, f"could not set {path}: {exc}") from exc
    return {"property": path, "value": _jsonable(getattr(target, attr))}


def report(ctx: Ctx, payload: dict) -> dict:
    return _report(_resolve_object(ctx, payload))


def add(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    physics_type = _physics_type(payload.get("type"))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        if physics_type == "RIGID_BODY":
            op = ctx.bpy.ops.rigidbody.object_add
            ctx.check_poll(op)
            op(type="ACTIVE")
        elif physics_type == "RIGID_BODY_CONSTRAINT":
            op = ctx.bpy.ops.rigidbody.constraint_add
            ctx.check_poll(op)
            op(type="FIXED")
        elif physics_type == "FIELD":
            if _physics_owner(obj, "FIELD") is None:
                op = ctx.bpy.ops.object.forcefield_toggle
                ctx.check_poll(op)
                op()
        else:
            op = ctx.bpy.ops.object.modifier_add
            ctx.check_poll(op)
            op(type=physics_type)
    return {"object": obj.name, "type": physics_type, "physics": _unit_report(_physics_owner(obj, physics_type, required=True))}


def remove(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    physics_type = _physics_type(payload.get("type"))
    owner = _physics_owner(obj, physics_type, required=True)
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        if physics_type == "RIGID_BODY":
            if owner is not None:
                op = ctx.bpy.ops.rigidbody.object_remove
                ctx.check_poll(op)
                op()
        elif physics_type == "RIGID_BODY_CONSTRAINT":
            if owner is not None:
                op = ctx.bpy.ops.rigidbody.constraint_remove
                ctx.check_poll(op)
                op()
        elif physics_type == "FIELD":
            if owner is not None:
                op = ctx.bpy.ops.object.forcefield_toggle
                ctx.check_poll(op)
                op()
        else:
            if owner is not None:
                op = ctx.bpy.ops.object.modifier_remove
                ctx.check_poll(op)
                op(modifier=getattr(owner, "name", ""))
    if physics_type == "FIELD":
        return {"object": obj.name, "type": physics_type, **_field_payload(obj)}
    return {"object": obj.name, "type": physics_type, "physics": _unit_report(_physics_owner(obj, physics_type))}


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    physics_type = _physics_type(payload.get("type"))
    owner = _physics_owner(obj, physics_type, required=True)
    change = _set_owner_property(ctx, obj, owner, _require_name(payload.get("property"), "property"), payload.get("value"))
    return {
        "object": obj.name,
        "type": physics_type,
        **change,
        "physics": _unit_report(_physics_owner(obj, physics_type, required=True)),
    }


def field_report(ctx: Ctx, payload: dict) -> dict:
    return _field_payload(_resolve_object(ctx, payload))


def field_set(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    field = _physics_owner(obj, "FIELD", required=True)
    change = _set_owner_property(ctx, obj, field, _require_name(payload.get("property"), "property"), payload.get("value"))
    return {"object": obj.name, **change, **_field_payload(obj)}


COMMANDS = [
    Command("physics.report", report, mutates=False),
    Command("physics.add", add, mutates=True, feedback="viewport"),
    Command("physics.remove", remove, mutates=True, feedback="viewport"),
    Command("physics.set", set_property, mutates=True, feedback="viewport"),
    Command("physics.field_report", field_report, mutates=False),
    Command("physics.field_set", field_set, mutates=True, feedback="viewport"),
]
