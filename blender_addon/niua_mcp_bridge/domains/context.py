"""Context / selection / mode handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command


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
    selected = _iter(getattr(bpy_ctx, "selected_objects", []))
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


COMMANDS = [
    Command("context.info", info, mutates=False),
    Command("context.areas", areas, mutates=False),
]
