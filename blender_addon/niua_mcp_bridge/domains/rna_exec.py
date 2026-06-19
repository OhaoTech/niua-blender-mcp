"""Generic RNA execution handlers: the long-tail escape hatch.

These three handlers let the agent run *any* operator and read/write *any* data
property without a hand-written ToolSpec, while still flowing through the kernel's
validate -> ctx.ensure -> undo pipeline.

``rna.call_operator`` is the important one: it getattr-resolves a ``bpy.ops`` operator,
validates/coerces the agent's args against the operator's ``get_rna_type().properties``
(dropping unknown keys, coercing numbers/enums, ignoring POINTER/COLLECTION props with a
note), sets up context via ``ctx.ensure(active/mode/select)`` and surfaces a failing
``poll()`` as a clean ``precondition_failed`` via ``ctx.check_poll``.

Args/values arrive as JSON-encoded strings (the kernel has no free-form object param
kind); we ``json.loads`` them here. ``bpy`` is only ever touched through ``ctx.bpy`` so
the module stays importable under fake-bpy unit tests.
"""

from __future__ import annotations

import json
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

# RNA property types we cannot coerce from JSON (need name->datablock resolution).
_UNSUPPORTED_PROP_TYPES = {"POINTER", "COLLECTION"}


def _parse_json(raw: Any, field: str, expect: type | tuple[type, ...] | None = None) -> Any:
    """Parse a JSON-encoded string param into a Python value, with a clean error."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, f"{field} must be a JSON-encoded string")
    raw = raw.strip()
    if raw == "":
        return None
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise BridgeError(INVALID_PARAMS, f"{field} is not valid JSON: {exc}") from exc
    if expect is not None and not isinstance(value, expect):
        raise BridgeError(INVALID_PARAMS, f"{field} must be a JSON {expect}")
    return value


def _coerce_value(prop: Any, value: Any) -> Any:
    """Best-effort coerce a JSON value to what an RNA property expects."""
    ptype = getattr(prop, "type", "")
    is_array = bool(getattr(prop, "is_array", False)) or int(getattr(prop, "array_length", 0) or 0) > 1
    if ptype in ("INT", "FLOAT"):
        cast = int if ptype == "INT" else float
        if isinstance(value, (list, tuple)):
            return [cast(v) for v in value]
        if isinstance(value, bool):  # JSON true/false should not silently become 1/0 here
            raise BridgeError(INVALID_PARAMS, f"{getattr(prop, 'identifier', '?')} expects a number")
        return cast(value)
    if ptype == "BOOLEAN":
        if isinstance(value, (list, tuple)):
            return [bool(v) for v in value]
        return bool(value)
    if ptype in ("STRING", "ENUM"):
        return value
    if is_array and isinstance(value, (list, tuple)):
        return list(value)
    return value


def _operator(ctx: Ctx, idname: str) -> Any:
    """getattr-resolve a 'cat.name' operator off bpy.ops, or fail cleanly.

    In real Blender ``getattr(bpy.ops.mesh, 'nope')`` returns a lazy callable stub that
    only errors later (at poll/call time, surfacing as a confusing precondition error).
    We probe ``get_rna_type()`` here so a truly nonexistent operator fails eagerly and
    honestly as ``not_found`` -- distinct from a real operator with the wrong context.
    """
    category, _, name = idname.partition(".")
    if not category or not name:
        raise BridgeError(INVALID_PARAMS, f"idname must be '<cat>.<name>', got: {idname!r}")
    try:
        op = getattr(getattr(ctx.bpy.ops, category), name)
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(NOT_FOUND, f"operator not found: {idname}", {"error": str(exc)}) from exc
    # Force resolution: a missing operator raises here rather than at call time.
    probe = getattr(op, "get_rna_type", None)
    if callable(probe):
        try:
            probe()
        except Exception as exc:  # noqa: BLE001
            raise BridgeError(NOT_FOUND, f"operator not found: {idname}", {"error": str(exc)}) from exc
    return op


def _validate_operator_args(op: Any, args: dict) -> tuple[dict, list[str], list[str]]:
    """Validate/coerce args against the operator's RNA. Return (clean, dropped, ignored)."""
    try:
        rna = op.get_rna_type()
        props = {
            getattr(p, "identifier", ""): p
            for p in getattr(rna, "properties", [])
            if getattr(p, "identifier", "") not in ("", "rna_type")
        }
    except Exception:  # noqa: BLE001 - if RNA is unreadable, pass args through untouched
        return dict(args), [], []

    clean: dict[str, Any] = {}
    dropped: list[str] = []
    ignored: list[str] = []
    for key, value in args.items():
        prop = props.get(key)
        if prop is None:
            dropped.append(key)
            continue
        if getattr(prop, "type", "") in _UNSUPPORTED_PROP_TYPES:
            ignored.append(key)
            continue
        clean[key] = _coerce_value(prop, value)
    return clean, dropped, ignored


def call_operator(ctx: Ctx, payload: dict) -> dict:
    idname = payload.get("idname")
    if not isinstance(idname, str) or not idname:
        raise BridgeError(INVALID_PARAMS, "idname is required, e.g. 'mesh.bevel'")

    args = _parse_json(payload.get("args"), "args", expect=dict) or {}
    select = _parse_json(payload.get("select"), "select", expect=list)
    obj = payload.get("object") if isinstance(payload.get("object"), str) and payload.get("object") else None
    mode = payload.get("mode") if isinstance(payload.get("mode"), str) and payload.get("mode") else None

    op = _operator(ctx, idname)
    clean, dropped, ignored = _validate_operator_args(op, args)

    with ctx.ensure(active=obj, mode=mode, select=select):
        ctx.check_poll(op)
        op(**clean)

    result: dict[str, Any] = {"operator": idname, "args": clean}
    if dropped:
        result["dropped_args"] = dropped
    if ignored:
        result["ignored_args"] = ignored
        result["note"] = "POINTER/COLLECTION args are not yet supported and were ignored"
    return result


def _resolve_parent(ctx: Ctx, path: str) -> tuple[Any, str]:
    """Walk a dotted path under bpy.data; return (parent_object, final_attr_name).

    Supports both attribute access (``foo.bar``) and collection lookup by name
    (``objects.Cube`` resolves Cube via the collection's ``[]``/``get``).
    """
    parts = [p for p in path.split(".") if p != ""]
    if not parts:
        raise BridgeError(INVALID_PARAMS, "path is required, e.g. 'objects.Cube.location'")

    current: Any = ctx.bpy.data
    for part in parts[:-1]:
        current = _step(current, part, path)
    return current, parts[-1]


def _step(current: Any, part: str, path: str) -> Any:
    """Resolve one path segment: attribute, then collection-by-name fallback."""
    if hasattr(current, part):
        return getattr(current, part)
    # Collection lookup by key (e.g. data.objects['Cube']).
    getter = getattr(current, "get", None)
    if callable(getter):
        found = getter(part)
        if found is not None:
            return found
    try:
        return current[part]  # type: ignore[index]
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(NOT_FOUND, f"path not found: {path} (at '{part}')", {"error": str(exc)}) from exc


def _read(current: Any, attr: str, path: str) -> Any:
    if hasattr(current, attr):
        return getattr(current, attr)
    getter = getattr(current, "get", None)
    if callable(getter):
        found = getter(attr)
        if found is not None:
            return found
    raise BridgeError(NOT_FOUND, f"path not found: {path} (at '{attr}')")


def _jsonable(value: Any) -> Any:
    """Render a value as something JSON-serializable for get_property results."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return [_jsonable(v) for v in value]  # vectors, colors, arrays
    except TypeError:
        return repr(value)


def get_property(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required, e.g. 'objects.Cube.location'")
    parent, attr = _resolve_parent(ctx, path)
    value = _read(parent, attr, path)
    return {"path": path, "value": _jsonable(value)}


def set_property(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required, e.g. 'objects.Cube.location'")
    if "value" not in payload:
        raise BridgeError(INVALID_PARAMS, "value is required (JSON-encoded)")
    value = _parse_json(payload.get("value"), "value")

    parent, attr = _resolve_parent(ctx, path)
    if not hasattr(parent, attr):
        raise BridgeError(NOT_FOUND, f"path not found: {path} (at '{attr}')")

    current = getattr(parent, attr)
    coerced = _coerce_to_existing(current, value)
    try:
        setattr(parent, attr, coerced)
    except Exception as exc:  # noqa: BLE001 - bad assignment -> clean precondition error
        raise BridgeError(
            PRECONDITION, f"cannot set {path}: {exc}", {"error": str(exc)}
        ) from exc
    return {"path": path, "value": _jsonable(getattr(parent, attr, coerced))}


def _coerce_to_existing(current: Any, value: Any) -> Any:
    """Coerce an incoming JSON value toward the type of the current attribute value."""
    if isinstance(current, bool):
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value) if not isinstance(value, (list, tuple)) else value
    if isinstance(current, float):
        return float(value) if not isinstance(value, (list, tuple)) else value
    return value


COMMANDS = [
    Command("rna.call_operator", call_operator, mutates=True, feedback="viewport"),
    Command("rna.set_property", set_property, mutates=True),
    Command("rna.get_property", get_property, mutates=False),
]
