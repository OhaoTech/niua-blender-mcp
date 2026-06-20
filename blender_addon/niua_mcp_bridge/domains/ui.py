"""UI automation / GUI parity handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command


def _iter(items: Any) -> list[Any]:
    try:
        return list(items or [])
    except TypeError:
        return []


def _name(item: Any) -> str | None:
    if item is None:
        return None
    return str(getattr(item, "name", "") or "") or None


def _rect(item: Any) -> dict[str, int]:
    return {
        "x": int(getattr(item, "x", 0) or 0),
        "y": int(getattr(item, "y", 0) or 0),
        "width": int(getattr(item, "width", 0) or 0),
        "height": int(getattr(item, "height", 0) or 0),
    }


def _regions(area: Any) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "type": str(getattr(region, "type", "") or ""),
            "rect": _rect(region),
        }
        for index, region in enumerate(_iter(getattr(area, "regions", [])))
    ]


def _areas(screen: Any) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "type": str(getattr(area, "type", "") or ""),
            "rect": _rect(area),
            "regions": _regions(area),
        }
        for index, area in enumerate(_iter(getattr(screen, "areas", [])))
    ]


def _windows(ctx: Ctx) -> list[dict[str, Any]]:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    wm = getattr(bpy_ctx, "window_manager", None)
    windows = []
    for index, window in enumerate(_iter(getattr(wm, "windows", []))):
        screen = getattr(window, "screen", None)
        workspace = getattr(window, "workspace", None) or getattr(bpy_ctx, "workspace", None)
        windows.append(
            {
                "index": index,
                "screen": _name(screen),
                "workspace": _name(workspace),
                "areas": _areas(screen),
            }
        )
    return windows


def _active_window(ctx: Ctx, windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    active = getattr(bpy_ctx, "window", None)
    wm = getattr(bpy_ctx, "window_manager", None)
    for index, window in enumerate(_iter(getattr(wm, "windows", []))):
        if window is active:
            screen = getattr(window, "screen", None)
            workspace = getattr(window, "workspace", None) or getattr(bpy_ctx, "workspace", None)
            return {"index": index, "screen": _name(screen), "workspace": _name(workspace)}
    if windows:
        first = windows[0]
        return {"index": first["index"], "screen": first["screen"], "workspace": first["workspace"]}
    return None


def _operator(ctx: Ctx, idname: str) -> Any | None:
    category, _, name = idname.partition(".")
    if not category or not name:
        return None
    try:
        return getattr(getattr(ctx.bpy.ops, category), name)
    except Exception:  # noqa: BLE001
        return None


def _poll_capability(ctx: Ctx, idname: str) -> dict[str, Any]:
    op = _operator(ctx, idname)
    if op is None:
        return {"available": False, "reason": f"operator not found: {idname}"}
    poll = getattr(op, "poll", None)
    try:
        available = bool(poll()) if callable(poll) else True
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    if not available:
        return {"available": False, "reason": f"{idname} is not available in the current UI context"}
    return {"available": True}


def _has_area(windows: list[dict[str, Any]]) -> bool:
    return any(window["areas"] for window in windows)


def _capabilities(ctx: Ctx, windows: list[dict[str, Any]]) -> dict[str, Any]:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    temp_override = getattr(bpy_ctx, "temp_override", None)
    context_override = _has_area(windows) and callable(temp_override)
    return {
        "context_override": {
            "available": bool(context_override),
            "reason": None if context_override else "no UI area with bpy.context.temp_override is available",
        },
        "screen_screenshot": _poll_capability(ctx, "screen.screenshot"),
        "redraw": _poll_capability(ctx, "wm.redraw_timer"),
        "keyboard_events": {
            "available": False,
            "reason": "OS-level keyboard event injection is not provided by this Blender Python bridge",
        },
        "mouse_events": {
            "available": False,
            "reason": "OS-level mouse event injection is not provided by this Blender Python bridge",
        },
    }


def windows(ctx: Ctx, payload: dict) -> dict:
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "windows": _windows(ctx),
    }


def state(ctx: Ctx, payload: dict) -> dict:
    records = _windows(ctx)
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "window_count": len(records),
        "active_window": _active_window(ctx, records),
        "capabilities": _capabilities(ctx, records),
    }


COMMANDS = [
    Command("ui.state", state, mutates=False),
    Command("ui.windows", windows, mutates=False),
]
