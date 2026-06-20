"""UI automation / GUI parity handlers."""

from __future__ import annotations

import os
from contextlib import nullcontext
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, PRECONDITION, BridgeError
from .rna_exec import _operator as _rna_operator
from .rna_exec import _parse_json, _validate_operator_args


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


def _require_idname(payload: dict) -> str:
    idname = payload.get("idname")
    if not isinstance(idname, str) or not idname:
        raise BridgeError(INVALID_PARAMS, "idname is required")
    return idname


def _require_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BridgeError(INVALID_PARAMS, f"{key} is required")
    return value


def _target_summary(
    override: bool,
    window_index: int | None = None,
    window: Any = None,
    area_index: int | None = None,
    area: Any = None,
    region_index: int | None = None,
    region: Any = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "override": bool(override),
        "window": None
        if window is None or window_index is None
        else {"index": window_index, "screen": _name(getattr(window, "screen", None)), "workspace": _name(getattr(window, "workspace", None))},
        "area": None if area is None or area_index is None else {"index": area_index, "type": str(getattr(area, "type", "") or "")},
        "region": None
        if region is None or region_index is None
        else {"index": region_index, "type": str(getattr(region, "type", "") or "")},
        "reason": reason,
    }


def _resolve_target(ctx: Ctx, payload: dict) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    area_type = str(payload.get("area", "VIEW_3D") or "VIEW_3D")
    region_type = str(payload.get("region", "WINDOW") or "WINDOW")
    window_index = int(payload.get("window_index", -1))
    area_index = int(payload.get("area_index", -1))
    bpy_ctx = getattr(ctx.bpy, "context", None)
    wm = getattr(bpy_ctx, "window_manager", None)
    windows = _iter(getattr(wm, "windows", []))
    if not windows:
        reason = "window not found: no Blender windows are available"
        return _target_summary(False, reason=reason), {}, reason

    candidates: list[tuple[int, Any]] = []
    if window_index >= 0:
        if window_index >= len(windows):
            reason = f"window not found: {window_index}"
            return _target_summary(False, reason=reason), {}, reason
        candidates = [(window_index, windows[window_index])]
    else:
        candidates = list(enumerate(windows))

    for w_index, window in candidates:
        screen = getattr(window, "screen", None)
        areas = _iter(getattr(screen, "areas", []))
        area_candidates: list[tuple[int, Any]] = []
        if area_index >= 0:
            if area_index < len(areas):
                area_candidates = [(area_index, areas[area_index])]
        else:
            area_candidates = list(enumerate(areas))
        for a_index, area in area_candidates:
            if area_type and str(getattr(area, "type", "") or "") != area_type:
                continue
            regions = _iter(getattr(area, "regions", []))
            region_match = next(
                (
                    (r_index, region)
                    for r_index, region in enumerate(regions)
                    if str(getattr(region, "type", "") or "") == region_type
                ),
                (None, None),
            )
            r_index, region = region_match
            override: dict[str, Any] = {"window": window, "area": area}
            if region is not None:
                override["region"] = region
            summary = _target_summary(True, w_index, window, a_index, area, r_index, region)
            return summary, override, None

    reason = f"area not found: {area_type}"
    return _target_summary(False, reason=reason), {}, reason


def _override_cm(ctx: Ctx, override: dict[str, Any]):
    if not override:
        return nullcontext()
    temp_override = getattr(getattr(ctx.bpy, "context", None), "temp_override", None)
    if callable(temp_override):
        return temp_override(**override)
    return nullcontext()


def _context_hints(payload: dict) -> tuple[str | None, str | None, list[Any] | None]:
    obj = payload.get("object") if isinstance(payload.get("object"), str) and payload.get("object") else None
    mode = payload.get("mode") if isinstance(payload.get("mode"), str) and payload.get("mode") else None
    select = _parse_json(payload.get("select"), "select", expect=list)
    return obj, mode, select


def _poll_op(op: Any) -> tuple[bool, str | None]:
    poll = getattr(op, "poll", None)
    try:
        available = bool(poll()) if callable(poll) else True
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if not available:
        return False, "operator poll returned false"
    return True, None


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


def operator_poll(ctx: Ctx, payload: dict) -> dict:
    idname = _require_idname(payload)
    op = _rna_operator(ctx, idname)
    target, override, target_reason = _resolve_target(ctx, payload)
    if target_reason and bool(payload.get("require_area", False)):
        return {"idname": idname, "available": False, "reason": target_reason, "ui_context": target}
    obj, mode, select = _context_hints(payload)
    try:
        with ctx.ensure(active=obj, mode=mode, select=select, area=""):
            with _override_cm(ctx, override):
                available, reason = _poll_op(op)
    except BridgeError as exc:
        return {"idname": idname, "available": False, "reason": exc.message, "ui_context": target}
    except Exception as exc:  # noqa: BLE001
        return {"idname": idname, "available": False, "reason": str(exc), "ui_context": target}
    if not available:
        return {"idname": idname, "available": False, "reason": reason, "ui_context": target}
    return {"idname": idname, "available": True, "ui_context": target}


def operator_invoke(ctx: Ctx, payload: dict) -> dict:
    idname = _require_idname(payload)
    args = _parse_json(payload.get("args"), "args", expect=dict) or {}
    select = _parse_json(payload.get("select"), "select", expect=list)
    obj = payload.get("object") if isinstance(payload.get("object"), str) and payload.get("object") else None
    mode = payload.get("mode") if isinstance(payload.get("mode"), str) and payload.get("mode") else None
    op = _rna_operator(ctx, idname)
    clean, dropped, ignored = _validate_operator_args(op, args)
    target, override, target_reason = _resolve_target(ctx, payload)
    if target_reason and bool(payload.get("require_area", False)):
        raise BridgeError(PRECONDITION, target_reason, {"ui_context": target})
    with ctx.ensure(active=obj, mode=mode, select=select, area=""):
        with _override_cm(ctx, override):
            available, reason = _poll_op(op)
            if not available:
                raise BridgeError(PRECONDITION, reason or "operator preconditions not met", {"ui_context": target})
            op(**clean)
    result: dict[str, Any] = {"operator": idname, "args": clean, "ui_context": target}
    if dropped:
        result["dropped_args"] = dropped
    if ignored:
        result["ignored_args"] = ignored
        result["note"] = "POINTER/COLLECTION args are not yet supported and were ignored"
    return result


def screenshot(ctx: Ctx, payload: dict) -> dict:
    path = _require_string(payload, "path")
    op = _operator(ctx, "screen.screenshot")
    capability = _poll_capability(ctx, "screen.screenshot")
    if not capability.get("available"):
        return capability
    try:
        op(filepath=path, full=bool(payload.get("full", False)))
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(PRECONDITION, f"screen.screenshot failed: {exc}", {"error": str(exc)}) from exc
    return {
        "available": True,
        "path": path,
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
        "applied": ["screen.screenshot"],
    }


def redraw(ctx: Ctx, payload: dict) -> dict:
    op = _operator(ctx, "wm.redraw_timer")
    capability = _poll_capability(ctx, "wm.redraw_timer")
    if not capability.get("available"):
        return capability
    redraw_type = str(payload.get("type", "DRAW_WIN_SWAP") or "DRAW_WIN_SWAP")
    iterations = int(payload.get("iterations", 1) or 1)
    try:
        op(type=redraw_type, iterations=iterations)
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(PRECONDITION, f"wm.redraw_timer failed: {exc}", {"error": str(exc)}) from exc
    return {
        "available": True,
        "applied": ["wm.redraw_timer"],
        "args": {"type": redraw_type, "iterations": iterations},
    }


COMMANDS = [
    Command("ui.state", state, mutates=False),
    Command("ui.windows", windows, mutates=False),
    Command("ui.operator_poll", operator_poll, mutates=False),
    Command("ui.operator_invoke", operator_invoke, mutates=True, feedback="viewport"),
    Command("ui.screenshot", screenshot, mutates=False),
    Command("ui.redraw", redraw, mutates=False),
]
