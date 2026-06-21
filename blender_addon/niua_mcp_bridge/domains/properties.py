"""Properties editor / RNA completeness handlers.

Stable paths use slash-separated segments under a namespaced root:

- ``object:Cube/location``
- ``object:Cube/data/use_auto_smooth``
- ``object:Cube/idprops/artist_note``
- ``object:Cube/modifiers/Bevel/width``

Object names and custom keys may be percent-encoded when they contain path
separators. Reports always emit encoded paths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

_COLLECTION_SEGMENTS = {"modifiers", "constraints", "material_slots"}


@dataclass
class _Resolved:
    kind: str
    owner: Any
    attr: str | None = None
    key: str | None = None
    base_path: str = ""


def _parse_json(raw: Any, field: str) -> Any:
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, f"{field} must be a JSON-encoded string")
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise BridgeError(INVALID_PARAMS, f"{field} is not valid JSON: {exc}") from exc


def _enc(value: str) -> str:
    return quote(str(value), safe="")


def _root_segments(path: str) -> tuple[str, list[str]]:
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required")
    root, sep, tail = path.partition(":")
    if sep != ":" or root not in {"object", "data"}:
        raise BridgeError(INVALID_PARAMS, "path must start with object:<name> or data:<collection>/<name>")
    parts = [unquote(part) for part in tail.split("/") if part != ""]
    if root == "object" and not parts:
        raise BridgeError(INVALID_PARAMS, "object path must include an object name")
    if root == "data" and len(parts) < 2:
        raise BridgeError(INVALID_PARAMS, "data path must include a collection and datablock name")
    return root, parts


def _collection_get(collection: Any, name: str, path: str) -> Any:
    getter = getattr(collection, "get", None)
    if callable(getter):
        found = getter(name)
        if found is not None:
            return found
    try:
        for item in collection:
            if getattr(item, "name", None) == name:
                return item
    except TypeError:
        pass
    raise BridgeError(NOT_FOUND, f"path not found: {path} (missing '{name}')")


def _is_collection_like(value: Any) -> bool:
    if isinstance(value, (str, bytes, dict)):
        return False
    if getattr(value, "bl_rna", None) is not None or callable(getattr(value, "keys", None)):
        return False
    if callable(getattr(value, "get", None)):
        return True
    try:
        iter(value)
    except Exception:  # noqa: BLE001 - ID-property owners may expose partial sequence APIs
        return False
    return not isinstance(value, (int, float, bool))


def _read_attr(owner: Any, attr: str, path: str) -> Any:
    if not hasattr(owner, attr):
        raise BridgeError(NOT_FOUND, f"path not found: {path} (at '{attr}')")
    try:
        return getattr(owner, attr)
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(PRECONDITION, f"cannot read {path}: {exc}", {"error": str(exc)}) from exc


def _resolve(ctx: Ctx, path: str) -> _Resolved:
    root, parts = _root_segments(path)
    if root == "object":
        object_name = parts[0]
        current = ctx.get_object(object_name)
        parts = parts[1:]
        base_path = f"object:{_enc(object_name)}"
    else:
        collection_name, item_name = parts[0], parts[1]
        collection = _read_attr(ctx.bpy.data, collection_name, path)
        current = _collection_get(collection, item_name, path)
        parts = parts[2:]
        base_path = f"data:{_enc(collection_name)}/{_enc(item_name)}"
    if not parts:
        return _Resolved("object", current, base_path=base_path)

    index = 0
    while index < len(parts):
        part = parts[index]
        if _is_collection_like(current) and not hasattr(current, part):
            current = _collection_get(current, part, path)
            index += 1
            continue
        if part == "idprops":
            if index + 1 >= len(parts):
                raise BridgeError(INVALID_PARAMS, "idprops path must include a key")
            if index + 2 != len(parts):
                raise BridgeError(INVALID_PARAMS, "nested idprops paths are not supported")
            return _Resolved("idprop", current, key=parts[index + 1], base_path=path)

        if part in _COLLECTION_SEGMENTS:
            if index + 1 >= len(parts):
                raise BridgeError(INVALID_PARAMS, f"{part} path must include an item name")
            collection = _read_attr(current, part, path)
            current = _collection_get(collection, parts[index + 1], path)
            index += 2
            continue

        if index == len(parts) - 1:
            return _Resolved("attr", current, attr=part, base_path=path)

        current = _read_attr(current, part, path)
        index += 1

    return _Resolved("object", current, base_path=path)


def _prop(owner: Any, identifier: str) -> Any | None:
    rna = getattr(owner, "bl_rna", None)
    for prop in getattr(rna, "properties", []) or []:
        if getattr(prop, "identifier", "") == identifier:
            return prop
    return None


def _ensure_writable(owner: Any, attr: str, path: str) -> None:
    prop = _prop(owner, attr)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {path}")


def _coerce_to_existing(current: Any, value: Any) -> Any:
    if isinstance(current, bool):
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value) if not isinstance(value, (list, tuple)) else value
    if isinstance(current, float):
        return float(value) if not isinstance(value, (list, tuple)) else value
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    name = getattr(value, "name", None)
    if getattr(value, "bl_rna", None) is not None or name is not None:
        out = {"name": str(name)} if name is not None else {"repr": repr(value)}
        vtype = getattr(value, "type", None)
        if vtype is not None:
            out["type"] = str(vtype)
        return out
    try:
        return [_jsonable(item) for item in value]
    except Exception:  # noqa: BLE001 - arbitrary bpy values may expose partial sequence APIs
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
    return {"count": len(items), "items": sample}


def _enum_items(prop: Any) -> list[dict[str, str]]:
    items = []
    for item in getattr(prop, "enum_items", []) or []:
        identifier = getattr(item, "identifier", "")
        if identifier:
            items.append({"identifier": str(identifier), "name": str(getattr(item, "name", identifier))})
    return items


def _property_report(owner: Any, prop: Any, base_path: str, include_values: bool) -> dict[str, Any]:
    identifier = str(getattr(prop, "identifier", "") or "")
    out: dict[str, Any] = {
        "identifier": identifier,
        "name": str(getattr(prop, "name", "") or identifier),
        "description": str(getattr(prop, "description", "") or ""),
        "type": str(getattr(prop, "type", "") or ""),
        "subtype": str(getattr(prop, "subtype", "") or ""),
        "is_readonly": bool(getattr(prop, "is_readonly", False)),
        "is_array": bool(getattr(prop, "is_array", False)),
        "array_length": int(getattr(prop, "array_length", 0) or 0),
        "path": f"{base_path}/{_enc(identifier)}",
    }
    enum_items = _enum_items(prop)
    if enum_items:
        out["enum_items"] = enum_items
    if include_values:
        try:
            value = getattr(owner, identifier)
        except Exception as exc:  # noqa: BLE001
            out["readable"] = False
            out["read_error"] = str(exc)
        else:
            out["readable"] = True
            if out["type"] == "COLLECTION":
                out["value"] = _collection_value(value)
            else:
                out["value"] = _jsonable(value)
    return out


def _rna_reports(owner: Any, base_path: str, include_values: bool) -> tuple[list[dict[str, Any]], list[str]]:
    reports = []
    missing = []
    for prop in getattr(getattr(owner, "bl_rna", None), "properties", []) or []:
        identifier = str(getattr(prop, "identifier", "") or "")
        if not identifier or identifier == "rna_type":
            continue
        reports.append(_property_report(owner, prop, base_path, include_values))
    seen = {report["identifier"] for report in reports}
    for prop in getattr(getattr(owner, "bl_rna", None), "properties", []) or []:
        identifier = str(getattr(prop, "identifier", "") or "")
        if identifier and identifier != "rna_type" and identifier not in seen:
            missing.append(identifier)
    return reports, missing


def _idprop_reports(owner: Any, base_path: str) -> list[dict[str, Any]]:
    keys = getattr(owner, "keys", None)
    if not callable(keys):
        return []
    reports = []
    for key in keys():
        key = str(key)
        if key == "_RNA_UI":
            continue
        try:
            value = owner[key]
        except Exception:  # noqa: BLE001
            continue
        reports.append({"key": key, "path": f"{base_path}/idprops/{_enc(key)}", "value": _jsonable(value)})
    reports.sort(key=lambda item: item["key"])
    return reports


def object_report(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("object")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(name)
    include_data = bool(payload.get("include_data", True))
    include_modifiers = bool(payload.get("include_modifiers", True))
    include_values = bool(payload.get("include_values", True))
    base_path = f"object:{_enc(name)}"

    object_properties, missing_object = _rna_reports(obj, base_path, include_values)
    result: dict[str, Any] = {
        "object": name,
        "type": str(getattr(obj, "type", "") or ""),
        "path": base_path,
        "object_properties": object_properties,
        "custom_properties": _idprop_reports(obj, base_path),
        "coverage": {
            "missing_object_properties": missing_object,
            "missing_data_properties": [],
            "missing_modifier_properties": {},
        },
    }

    data = getattr(obj, "data", None)
    if include_data and data is not None:
        data_path = f"{base_path}/data"
        data_properties, missing_data = _rna_reports(data, data_path, include_values)
        result["data"] = {
            "name": str(getattr(data, "name", "") or ""),
            "type": str(getattr(getattr(data, "bl_rna", None), "identifier", "") or type(data).__name__),
            "path": data_path,
            "properties": data_properties,
            "custom_properties": _idprop_reports(data, data_path),
        }
        result["coverage"]["missing_data_properties"] = missing_data

    modifiers = []
    if include_modifiers:
        for modifier in list(getattr(obj, "modifiers", []) or []):
            modifier_name = str(getattr(modifier, "name", "") or "")
            modifier_path = f"{base_path}/modifiers/{_enc(modifier_name)}"
            modifier_properties, missing_modifier = _rna_reports(modifier, modifier_path, include_values)
            modifiers.append(
                {
                    "name": modifier_name,
                    "type": str(getattr(modifier, "type", "") or ""),
                    "path": modifier_path,
                    "properties": modifier_properties,
                }
            )
            if missing_modifier:
                result["coverage"]["missing_modifier_properties"][modifier_name] = missing_modifier
    result["modifiers"] = modifiers
    return result


def report(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    include_values = bool(payload.get("include_values", True))
    resolved = _resolve(ctx, path)
    if resolved.kind == "idprop":
        target = resolved.owner[resolved.key]
        base_path = path
    elif resolved.kind == "attr":
        assert resolved.attr is not None
        target = _read_attr(resolved.owner, resolved.attr, path)
        base_path = path
    else:
        target = resolved.owner
        base_path = resolved.base_path or path

    if getattr(target, "bl_rna", None) is None:
        raise BridgeError(PRECONDITION, f"path target has no RNA properties: {path}")
    properties, missing = _rna_reports(target, base_path, include_values)
    return {
        "path": base_path,
        "name": str(getattr(target, "name", "") or ""),
        "type": str(getattr(target, "type", "") or getattr(type(target), "__name__", "")),
        "properties": properties,
        "custom_properties": _idprop_reports(target, base_path),
        "coverage": {"missing_properties": missing},
    }


def get(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    resolved = _resolve(ctx, path)
    if resolved.kind == "idprop":
        keys = getattr(resolved.owner, "keys", None)
        if not callable(keys) or resolved.key not in keys():
            raise BridgeError(NOT_FOUND, f"path not found: {path} (at '{resolved.key}')")
        return {"path": path, "value": _jsonable(resolved.owner[resolved.key])}
    if resolved.kind == "object":
        return {"path": path, "value": _jsonable(resolved.owner)}
    assert resolved.attr is not None
    return {"path": path, "value": _jsonable(_read_attr(resolved.owner, resolved.attr, path))}


def set(ctx: Ctx, payload: dict) -> dict:  # noqa: A001 - command name mirrors API
    path = payload.get("path")
    if "value" not in payload:
        raise BridgeError(INVALID_PARAMS, "value is required (JSON-encoded)")
    value = _parse_json(payload.get("value"), "value")
    resolved = _resolve(ctx, path)
    if resolved.kind == "idprop":
        resolved.owner[resolved.key] = value
        return {"path": path, "value": _jsonable(resolved.owner[resolved.key])}
    if resolved.kind == "object":
        raise BridgeError(INVALID_PARAMS, "cannot assign an entire object")
    assert resolved.attr is not None
    if not hasattr(resolved.owner, resolved.attr):
        raise BridgeError(NOT_FOUND, f"path not found: {path} (at '{resolved.attr}')")
    _ensure_writable(resolved.owner, resolved.attr, path)
    current = getattr(resolved.owner, resolved.attr)
    try:
        setattr(resolved.owner, resolved.attr, _coerce_to_existing(current, value))
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(PRECONDITION, f"cannot set {path}: {exc}", {"error": str(exc)}) from exc
    return {"path": path, "value": _jsonable(getattr(resolved.owner, resolved.attr))}


def unset(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    resolved = _resolve(ctx, path)
    if resolved.kind == "idprop":
        keys = getattr(resolved.owner, "keys", None)
        if not callable(keys) or resolved.key not in keys():
            raise BridgeError(NOT_FOUND, f"path not found: {path} (at '{resolved.key}')")
        del resolved.owner[resolved.key]
        return {"path": path, "removed": True}
    if resolved.kind == "object":
        raise BridgeError(INVALID_PARAMS, "cannot unset an entire object")
    assert resolved.attr is not None
    _ensure_writable(resolved.owner, resolved.attr, path)
    unsetter = getattr(resolved.owner, "property_unset", None)
    if not callable(unsetter):
        raise BridgeError(PRECONDITION, f"property cannot be unset: {path}")
    try:
        unsetter(resolved.attr)
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(PRECONDITION, f"cannot unset {path}: {exc}", {"error": str(exc)}) from exc
    return {"path": path, "removed": True}


COMMANDS = [
    Command("properties.report", report, mutates=False),
    Command("properties.object_report", object_report, mutates=False),
    Command("properties.get", get, mutates=False),
    Command("properties.set", set, mutates=True, feedback="viewport"),
    Command("properties.unset", unset, mutates=True, feedback="viewport"),
]
