"""Modifiers domain handlers: add, set, apply, remove, list.

Handlers stay tiny: the kernel does validation, undo and (for the operators) context.
``add``/``set``/``list`` work directly on the object's ``modifiers`` collection.
``apply``/``remove`` go through ``bpy.ops.object.modifier_apply``/``modifier_remove``
wrapped in ``ctx.ensure(active=obj, mode="OBJECT", select=[obj])`` so the active
object is guaranteed and restored; a failing ``poll()`` (e.g. multi-user mesh, wrong
mode) surfaces as a clean ``precondition_failed`` via ``ctx.check_poll``.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

_SCALAR_RNA_TYPES = {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}


def _resolve_object(ctx: Ctx, payload: dict) -> Any:
    """Return the target object (named, else active); fail cleanly otherwise."""
    name = payload.get("object")
    if isinstance(name, str) and name:
        return ctx.get_object(name)
    view_layer = getattr(ctx.bpy.context, "view_layer", None)
    obj = getattr(getattr(view_layer, "objects", None), "active", None)
    if obj is None:
        obj = getattr(ctx.bpy.context, "object", None)
    if obj is None:
        raise BridgeError(PRECONDITION, "no active object; pass 'object'")
    return obj


def _get_modifier(obj: Any, name: str) -> Any:
    """Look up a modifier by name on an object, else raise not_found."""
    modifiers = getattr(obj, "modifiers", None)
    getter = getattr(modifiers, "get", None)
    mod = getter(name) if callable(getter) else None
    if mod is None:
        raise BridgeError(
            NOT_FOUND,
            f"modifier not found: {name}",
            {"object": getattr(obj, "name", "?")},
        )
    return mod


def _modifier_list(obj: Any) -> list[Any]:
    return list(getattr(obj, "modifiers", []) or [])


def _modifier_index(obj: Any, mod: Any) -> int:
    for index, candidate in enumerate(_modifier_list(obj)):
        if candidate is mod or getattr(candidate, "name", None) == getattr(mod, "name", None):
            return index
    return -1


def _modifier_type_items(ctx: Ctx) -> list[Any]:
    modifier_type = getattr(getattr(ctx.bpy, "types", None), "Modifier", None)
    bl_rna = getattr(modifier_type, "bl_rna", None)
    properties = getattr(bl_rna, "properties", None)
    prop = None
    if properties is not None:
        try:
            prop = properties["type"]
        except (KeyError, TypeError, AttributeError):
            getter = getattr(properties, "get", None)
            prop = getter("type") if callable(getter) else None
    return list(getattr(prop, "enum_items", []) or [])


def _scalar_value(value: Any) -> Any:
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return value
    return None


def _modifier_properties(mod: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    bl_rna = getattr(mod, "bl_rna", None)
    properties = getattr(bl_rna, "properties", None)
    if properties is not None:
        for prop in list(properties):
            ident = getattr(prop, "identifier", "")
            if ident in {"rna_type"} or not ident:
                continue
            if getattr(prop, "type", None) not in _SCALAR_RNA_TYPES:
                continue
            try:
                value = getattr(mod, ident)
            except Exception:  # noqa: BLE001 - some RNA properties can raise on access
                continue
            scalar = _scalar_value(value)
            if scalar is not None:
                out[ident] = scalar
        return out

    for ident, value in vars(mod).items():
        if ident.startswith("_") or ident in {"node_group"}:
            continue
        scalar = _scalar_value(value)
        if scalar is not None:
            out[ident] = scalar
    return out


def _modifier_report(mod: Any, index: int) -> dict[str, Any]:
    node_group = getattr(mod, "node_group", None)
    return {
        "index": index,
        "name": getattr(mod, "name", ""),
        "type": getattr(mod, "type", ""),
        "show_viewport": bool(getattr(mod, "show_viewport", True)),
        "show_render": bool(getattr(mod, "show_render", True)),
        "show_in_editmode": bool(getattr(mod, "show_in_editmode", False)),
        "show_on_cage": bool(getattr(mod, "show_on_cage", False)),
        "show_expanded": bool(getattr(mod, "show_expanded", True)),
        "is_active": bool(getattr(mod, "is_active", False)),
        "execution_time": float(getattr(mod, "execution_time", 0.0) or 0.0),
        "node_group": getattr(node_group, "name", None) if node_group is not None else None,
        "properties": _modifier_properties(mod),
    }


def _coerce_value(current: Any, value: Any) -> Any:
    """Coerce an incoming string value toward the existing property's type."""
    if not isinstance(value, str):
        return value
    if isinstance(current, bool):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise BridgeError(INVALID_PARAMS, f"expected a boolean, got: {value!r}")
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except ValueError as exc:
            raise BridgeError(INVALID_PARAMS, f"expected an integer, got: {value!r}") from exc
    if isinstance(current, float):
        try:
            return float(value)
        except ValueError as exc:
            raise BridgeError(INVALID_PARAMS, f"expected a number, got: {value!r}") from exc
    return value


def types_list(ctx: Ctx, payload: dict) -> dict:
    return {
        "types": [
            {
                "identifier": getattr(item, "identifier", ""),
                "name": getattr(item, "name", ""),
            }
            for item in _modifier_type_items(ctx)
        ]
    }


def add(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    mod_type = str(payload.get("type", "")).upper()
    name = payload.get("name")
    label = name if isinstance(name, str) and name else mod_type
    try:
        mod = obj.modifiers.new(name=label, type=mod_type)
    except (TypeError, RuntimeError) as exc:
        raise BridgeError(
            PRECONDITION,
            f"could not add modifier of type {mod_type}: {exc}",
            {"object": getattr(obj, "name", "?"), "type": mod_type},
        ) from exc
    if mod is None:
        raise BridgeError(
            PRECONDITION,
            f"object does not support modifiers: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    return {"object": obj.name, "modifier": mod.name, "type": mod_type}


def set_property(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    name = str(payload.get("name", ""))
    prop = str(payload.get("property", ""))
    mod = _get_modifier(obj, name)
    if not hasattr(mod, prop):
        raise BridgeError(
            INVALID_PARAMS,
            f"modifier has no property: {prop}",
            {"modifier": name, "type": getattr(mod, "type", None)},
        )
    value = _coerce_value(getattr(mod, prop), payload.get("value"))
    try:
        setattr(mod, prop, value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise BridgeError(
            INVALID_PARAMS,
            f"could not set {prop}={value!r}: {exc}",
            {"modifier": name},
        ) from exc
    return {"object": obj.name, "modifier": name, "property": prop, "value": getattr(mod, prop)}


def set_visibility(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    name = str(payload.get("name", ""))
    mod = _get_modifier(obj, name)
    flags = {
        "viewport": "show_viewport",
        "render": "show_render",
        "editmode": "show_in_editmode",
        "cage": "show_on_cage",
        "expanded": "show_expanded",
    }
    for param, attr in flags.items():
        if param in payload:
            setattr(mod, attr, bool(payload[param]))
    return {"object": obj.name, "modifier": _modifier_report(mod, _modifier_index(obj, mod))}


def move(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    name = str(payload.get("name", ""))
    _get_modifier(obj, name)
    index = int(payload.get("index", 0))
    op = ctx.bpy.ops.object.modifier_move_to_index
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(op)
        op(modifier=name, index=index)
    mod = _get_modifier(obj, name)
    return {"object": obj.name, "modifier": _modifier_report(mod, _modifier_index(obj, mod))}


def copy(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    name = str(payload.get("name", ""))
    _get_modifier(obj, name)
    before_names = {getattr(mod, "name", "") for mod in _modifier_list(obj)}
    op = ctx.bpy.ops.object.modifier_copy
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(op)
        op(modifier=name)
    after = _modifier_list(obj)
    copied = next((mod for mod in after if getattr(mod, "name", "") not in before_names), None)
    if copied is None and after:
        copied = after[-1]
    if copied is None:
        raise BridgeError(PRECONDITION, f"modifier copy did not create a modifier: {name}")
    new_name = payload.get("new_name")
    if isinstance(new_name, str) and new_name:
        copied.name = new_name
    return {"object": obj.name, "modifier": _modifier_report(copied, _modifier_index(obj, copied))}


def apply(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    name = str(payload.get("name", ""))
    _get_modifier(obj, name)  # validate existence -> clean not_found before any op
    op = ctx.bpy.ops.object.modifier_apply
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(op)
        op(modifier=name)
    return {"object": obj.name, "modifier": name, "applied": True}


def remove(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    name = str(payload.get("name", ""))
    _get_modifier(obj, name)  # validate existence -> clean not_found before any op
    op = ctx.bpy.ops.object.modifier_remove
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(op)
        op(modifier=name)
    return {"object": obj.name, "modifier": name, "removed": True}


def list_modifiers(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    modifiers = getattr(obj, "modifiers", []) or []
    return {
        "object": obj.name,
        "modifiers": [_modifier_report(m, index) for index, m in enumerate(modifiers)],
    }


COMMANDS = [
    Command("modifiers.types", types_list, mutates=False),
    Command("modifiers.add", add, mutates=True, feedback="viewport"),
    Command("modifiers.set", set_property, mutates=True, feedback="viewport"),
    Command("modifiers.set_visibility", set_visibility, mutates=True, feedback="viewport"),
    Command("modifiers.move", move, mutates=True, feedback="viewport"),
    Command("modifiers.copy", copy, mutates=True, feedback="viewport"),
    Command("modifiers.apply", apply, mutates=True, feedback="viewport"),
    Command("modifiers.remove", remove, mutates=True, feedback="viewport"),
    Command("modifiers.list", list_modifiers, mutates=False),
]
