"""Particles GUI-parity handlers."""

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


def _system_list(obj: Any) -> list[Any]:
    return list(getattr(obj, "particle_systems", []) or [])


def _get_system(obj: Any, name: Any) -> Any:
    system_name = _require_name(name, "particle system name")
    systems = getattr(obj, "particle_systems", None)
    getter = getattr(systems, "get", None)
    psys = getter(system_name) if callable(getter) else None
    if psys is None:
        psys = next((candidate for candidate in _system_list(obj) if getattr(candidate, "name", None) == system_name), None)
    if psys is None:
        raise BridgeError(NOT_FOUND, f"particle system not found: {system_name}", {"object": getattr(obj, "name", "?")})
    return psys


def _index_of(obj: Any, psys: Any) -> int:
    for index, candidate in enumerate(_system_list(obj)):
        if candidate is psys or getattr(candidate, "name", None) == getattr(psys, "name", None):
            return index
    return -1


def _set_active(obj: Any, psys: Any) -> None:
    systems = getattr(obj, "particle_systems", None)
    if systems is not None and hasattr(systems, "active_index"):
        systems.active_index = max(0, _index_of(obj, psys))


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
        except Exception as exc:  # noqa: BLE001 - some particle RNA can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _compact_system(obj: Any, psys: Any) -> dict[str, Any]:
    settings = getattr(psys, "settings", None)
    return {
        "index": _index_of(obj, psys),
        "name": getattr(psys, "name", ""),
        "settings": {
            "name": getattr(settings, "name", None),
            "type": getattr(settings, "type", None),
            "count": getattr(settings, "count", None),
            "frame_start": getattr(settings, "frame_start", None),
            "frame_end": getattr(settings, "frame_end", None),
        },
    }


def _system_report(obj: Any, psys: Any) -> dict[str, Any]:
    settings = getattr(psys, "settings", None)
    out = _compact_system(obj, psys)
    out["properties"] = _properties_report(psys)
    out["settings"]["properties"] = _properties_report(settings) if settings is not None else {}
    return out


def _systems_payload(obj: Any) -> dict[str, Any]:
    systems = [_compact_system(obj, psys) for psys in _system_list(obj)]
    return {"object": obj.name, "system_count": len(systems), "systems": systems}


def _report_payload(obj: Any, name: Any = "") -> dict[str, Any]:
    if isinstance(name, str) and name:
        psys = _get_system(obj, name)
        return {"object": obj.name, "particle_system": _system_report(obj, psys)}
    reports = [_system_report(obj, psys) for psys in _system_list(obj)]
    return {"object": obj.name, "system_count": len(reports), "systems": reports}


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


def _resolve_property(psys: Any, path: str) -> tuple[Any, str]:
    if not isinstance(path, str) or not path:
        raise BridgeError(PRECONDITION, "property is required")
    settings = getattr(psys, "settings", None)
    if path.startswith("settings."):
        if settings is None:
            raise BridgeError(NOT_FOUND, "particle system has no settings")
        owner = settings
        attr = path.split(".", 1)[1]
    elif hasattr(psys, path):
        owner = psys
        attr = path
    elif settings is not None and hasattr(settings, path):
        owner = settings
        attr = path
    else:
        raise BridgeError(INVALID_PARAMS, f"particle property not found: {path}")
    if "." in attr:
        current = owner
        parts = attr.split(".")
        for part in parts[:-1]:
            if not hasattr(current, part):
                raise BridgeError(INVALID_PARAMS, f"particle property path not found: {path}")
            current = getattr(current, part)
        owner = current
        attr = parts[-1]
    return owner, attr


def systems(ctx: Ctx, payload: dict) -> dict:
    return _systems_payload(_resolve_object(ctx, payload))


def add(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    before = set(id(psys) for psys in _system_list(obj))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        op = ctx.bpy.ops.object.particle_system_add
        ctx.check_poll(op)
        op()
    created = next((psys for psys in reversed(_system_list(obj)) if id(psys) not in before), None)
    if created is None and _system_list(obj):
        created = _system_list(obj)[-1]
    if created is None:
        raise BridgeError(PRECONDITION, "no particle system was created")
    name = payload.get("name")
    if isinstance(name, str) and name:
        created.name = name
    return {"object": obj.name, "particle_system": _compact_system(obj, created)}


def remove(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    psys = _get_system(obj, payload.get("name"))
    _set_active(obj, psys)
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        op = ctx.bpy.ops.object.particle_system_remove
        ctx.check_poll(op)
        op()
    return _systems_payload(obj)


def report(ctx: Ctx, payload: dict) -> dict:
    return _report_payload(_resolve_object(ctx, payload), payload.get("name", ""))


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    psys = _get_system(obj, payload.get("name"))
    path = _require_name(payload.get("property"), "property")
    owner, attr = _resolve_property(psys, path)
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
        "name": getattr(psys, "name", ""),
        "property": path,
        "value": _jsonable(getattr(owner, attr)),
        "particle_system": _system_report(obj, psys),
    }


COMMANDS = [
    Command("particles.systems", systems, mutates=False),
    Command("particles.add", add, mutates=True, feedback="viewport"),
    Command("particles.remove", remove, mutates=True, feedback="viewport"),
    Command("particles.report", report, mutates=False),
    Command("particles.set", set_property, mutates=True, feedback="viewport"),
]
