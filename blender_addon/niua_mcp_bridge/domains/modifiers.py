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
        "modifiers": [
            {
                "name": getattr(m, "name", ""),
                "type": getattr(m, "type", ""),
                "show_viewport": bool(getattr(m, "show_viewport", True)),
            }
            for m in modifiers
        ],
    }


COMMANDS = [
    Command("modifiers.add", add, mutates=True, feedback="viewport"),
    Command("modifiers.set", set_property, mutates=True, feedback="viewport"),
    Command("modifiers.apply", apply, mutates=True, feedback="viewport"),
    Command("modifiers.remove", remove, mutates=True, feedback="viewport"),
    Command("modifiers.list", list_modifiers, mutates=False),
]
