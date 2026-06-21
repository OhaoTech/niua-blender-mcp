"""Statusbar GUI-parity handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command


def _items(value: Any) -> list[Any]:
    try:
        return list(value or [])
    except TypeError:
        return []


def _name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(getattr(value, "name", "") or "")
    return text or None


def _areas(ctx: Ctx, area_type: str) -> list[dict[str, Any]]:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    wm = getattr(bpy_ctx, "window_manager", None)
    records: list[dict[str, Any]] = []
    for window_index, window in enumerate(_items(getattr(wm, "windows", []))):
        screen = getattr(window, "screen", None)
        workspace = getattr(window, "workspace", None) or getattr(bpy_ctx, "workspace", None)
        for area_index, area in enumerate(_items(getattr(screen, "areas", []))):
            if str(getattr(area, "type", "") or "") != area_type:
                continue
            records.append(
                {
                    "window_index": window_index,
                    "screen": _name(screen),
                    "workspace": _name(workspace),
                    "area_index": area_index,
                    "type": area_type,
                    "region_count": len(_items(getattr(area, "regions", []))),
                }
            )
    return records


def _context_name(ctx: Ctx, attr: str) -> str | None:
    return _name(getattr(getattr(ctx.bpy, "context", None), attr, None))


def _scene_statistics(ctx: Ctx) -> tuple[str | None, str | None]:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    scene = getattr(bpy_ctx, "scene", None)
    statistics = getattr(scene, "statistics", None)
    if not callable(statistics):
        return None, "scene statistics are not available"
    try:
        return str(statistics(getattr(bpy_ctx, "view_layer", None))), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def report(ctx: Ctx, payload: dict) -> dict:
    areas = _areas(ctx, "STATUSBAR")
    stats, stats_error = _scene_statistics(ctx)
    out: dict[str, Any] = {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "workspace": _context_name(ctx, "workspace"),
        "screen": _context_name(ctx, "screen"),
        "scene": _context_name(ctx, "scene"),
        "mode": str(getattr(getattr(ctx.bpy, "context", None), "mode", "") or ""),
        "area_count": len(areas),
        "areas": areas,
        "scene_statistics": stats,
        "status_text": {
            "available": False,
            "reason": "Blender status text is runtime UI state and has no stable RNA getter",
        },
    }
    if stats_error:
        out["scene_statistics_error"] = stats_error
    return out


COMMANDS = [Command("statusbar.report", report, mutates=False)]
