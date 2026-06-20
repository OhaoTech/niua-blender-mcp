"""Context / selection / mode handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, PRECONDITION, BridgeError


def _name(item: Any) -> str | None:
    if item is None:
        return None
    return str(getattr(item, "name", "") or "")


def _iter(items: Any) -> list[Any]:
    try:
        return list(items or [])
    except TypeError:
        return []


def _object_summary(obj: Any) -> dict[str, Any] | None:
    if obj is None:
        return None
    visible_get = getattr(obj, "visible_get", None)
    visible = bool(visible_get()) if callable(visible_get) else not bool(getattr(obj, "hide_viewport", False))
    return {
        "name": _name(obj),
        "type": str(getattr(obj, "type", "") or ""),
        "mode": str(getattr(obj, "mode", "") or ""),
        "selected": bool(getattr(obj, "select_get", lambda: False)()),
        "visible": visible,
        "selectable": not bool(getattr(obj, "hide_select", False)),
    }


def _scene_objects(ctx: Ctx) -> list[Any]:
    return _iter(getattr(getattr(ctx.bpy.context, "scene", None), "objects", []))


def _selected_objects(ctx: Ctx) -> list[Any]:
    selected = getattr(ctx.bpy.context, "selected_objects", None)
    if selected is not None:
        return _iter(selected)
    return [obj for obj in _scene_objects(ctx) if bool(getattr(obj, "select_get", lambda: False)())]


def _split_names(raw: Any, field: str = "objects") -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        raise BridgeError(INVALID_PARAMS, f"{field} is required")
    return [name.strip() for name in raw.split(",") if name.strip()]


def _get_object(ctx: Ctx, name: str) -> Any:
    return ctx.get_object(name)


def _check_selectable(obj: Any) -> None:
    if bool(getattr(obj, "hide_viewport", False)):
        raise BridgeError(PRECONDITION, f"object is hidden in viewport: {_name(obj)}")
    if bool(getattr(obj, "hide_select", False)):
        raise BridgeError(PRECONDITION, f"object is not selectable: {_name(obj)}")


def _set_selected(obj: Any, selected: bool) -> None:
    setter = getattr(obj, "select_set", None)
    if callable(setter):
        setter(bool(selected))


def _set_active(ctx: Ctx, obj: Any, select: bool = True) -> None:
    _check_selectable(obj)
    view_layer = getattr(ctx.bpy.context, "view_layer", None)
    objects = getattr(view_layer, "objects", None)
    if objects is None:
        raise BridgeError(PRECONDITION, "active object slot is unavailable")
    objects.active = obj
    if select:
        _set_selected(obj, True)


def _mesh_select_mode(ctx: Any) -> dict[str, bool]:
    values = list(getattr(getattr(ctx, "tool_settings", None), "mesh_select_mode", []) or [])
    values = (values + [False, False, False])[:3]
    return {"vertex": bool(values[0]), "edge": bool(values[1]), "face": bool(values[2])}


def _areas(ctx: Any) -> dict[str, Any]:
    wm = getattr(ctx, "window_manager", None)
    windows = []
    has_view3d = False
    for w_index, window in enumerate(_iter(getattr(wm, "windows", []))):
        screen = getattr(window, "screen", None)
        areas = []
        for a_index, area in enumerate(_iter(getattr(screen, "areas", []))):
            area_type = str(getattr(area, "type", "") or "")
            if area_type == "VIEW_3D":
                has_view3d = True
            areas.append(
                {
                    "index": a_index,
                    "type": area_type,
                    "regions": [str(getattr(region, "type", "") or "") for region in _iter(getattr(area, "regions", []))],
                }
            )
        windows.append({"index": w_index, "screen": _name(screen), "areas": areas})
    return {"has_view3d": has_view3d, "windows": windows}


def _context_summary(ctx: Ctx) -> dict[str, Any]:
    bpy_ctx = ctx.bpy.context
    view_layer = getattr(bpy_ctx, "view_layer", None)
    active = getattr(getattr(view_layer, "objects", None), "active", None)
    selected = _selected_objects(ctx)
    return {
        "scene": _name(getattr(bpy_ctx, "scene", None)),
        "view_layer": _name(view_layer),
        "workspace": _name(getattr(bpy_ctx, "workspace", None)),
        "context_mode": str(getattr(bpy_ctx, "mode", "") or ""),
        "object_mode": str(getattr(active, "mode", "") or ""),
        "active": _object_summary(active),
        "selected": [_object_summary(obj) for obj in selected],
        "mesh_select_mode": _mesh_select_mode(bpy_ctx),
        "areas": _areas(bpy_ctx),
    }


def info(ctx: Ctx, payload: dict) -> dict:
    return _context_summary(ctx)


def areas(ctx: Ctx, payload: dict) -> dict:
    return _areas(ctx.bpy.context)


def set_active(ctx: Ctx, payload: dict) -> dict:
    obj = _get_object(ctx, str(payload.get("object", "")))
    _set_active(ctx, obj, bool(payload.get("select", True)))
    return _context_summary(ctx)


def select_objects(ctx: Ctx, payload: dict) -> dict:
    names = _split_names(payload.get("objects"))
    action = str(payload.get("action", "REPLACE") or "REPLACE").upper()
    objects = [_get_object(ctx, name) for name in names]
    for obj in objects:
        _check_selectable(obj)
    if action not in {"REPLACE", "ADD", "REMOVE", "TOGGLE"}:
        raise BridgeError(INVALID_PARAMS, f"unsupported selection action: {action}")
    if action == "REPLACE":
        targets = set(objects)
        for obj in _scene_objects(ctx):
            _set_selected(obj, obj in targets)
    elif action == "ADD":
        for obj in objects:
            _set_selected(obj, True)
    elif action == "REMOVE":
        for obj in objects:
            _set_selected(obj, False)
    else:
        for obj in objects:
            current = bool(getattr(obj, "select_get", lambda: False)())
            _set_selected(obj, not current)

    active_name = payload.get("active")
    if isinstance(active_name, str) and active_name:
        active = _get_object(ctx, active_name)
        if not bool(getattr(active, "select_get", lambda: False)()):
            raise BridgeError(PRECONDITION, "active object must be selected after selection action")
        _set_active(ctx, active, select=False)
    return _context_summary(ctx)


def select_all(ctx: Ctx, payload: dict) -> dict:
    action = str(payload.get("action", "DESELECT") or "DESELECT").upper()
    if action not in {"SELECT", "DESELECT", "INVERT"}:
        raise BridgeError(INVALID_PARAMS, f"unsupported select_all action: {action}")
    for obj in _scene_objects(ctx):
        if action == "SELECT":
            _check_selectable(obj)
            _set_selected(obj, True)
        elif action == "DESELECT":
            _set_selected(obj, False)
        else:
            if bool(getattr(obj, "select_get", lambda: False)()):
                _set_selected(obj, False)
            else:
                _check_selectable(obj)
                _set_selected(obj, True)
    return _context_summary(ctx)


COMMANDS = [
    Command("context.info", info, mutates=False),
    Command("context.areas", areas, mutates=False),
    Command("context.set_active", set_active, mutates=True, feedback="viewport"),
    Command("context.select_objects", select_objects, mutates=True, feedback="viewport"),
    Command("context.select_all", select_all, mutates=True, feedback="viewport"),
]
