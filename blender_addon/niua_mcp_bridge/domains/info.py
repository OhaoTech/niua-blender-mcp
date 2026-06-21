"""Info editor GUI-parity handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError

_INFO_OPERATORS = (
    "report_copy",
    "report_delete",
    "report_replay",
    "reports_display_update",
    "select_all",
    "select_box",
    "select_pick",
)


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


def _regions(area: Any) -> list[dict[str, Any]]:
    return [
        {"index": index, "type": str(getattr(region, "type", "") or "")}
        for index, region in enumerate(_items(getattr(area, "regions", [])))
    ]


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
                    "regions": _regions(area),
                }
            )
    return records


def _operator_status(ctx: Ctx, name: str) -> dict[str, Any]:
    info_ops = getattr(getattr(ctx.bpy, "ops", None), "info", None)
    op = getattr(info_ops, name, None)
    if op is None:
        return {"available": False, "reason": f"operator not found: info.{name}"}
    poll = getattr(op, "poll", None)
    try:
        available = bool(poll()) if callable(poll) else True
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    if not available:
        return {"available": False, "reason": "operator poll returned false"}
    return {"available": True}


def _limit(payload: dict, default: int) -> int:
    raw = payload.get("limit", default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise BridgeError(INVALID_PARAMS, "limit must be an integer") from exc
    if value < 0:
        raise BridgeError(INVALID_PARAMS, "limit must be >= 0")
    return value


def report(ctx: Ctx, payload: dict) -> dict:
    areas = _areas(ctx, "INFO")
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "area_count": len(areas),
        "areas": areas,
        "operators": {name: _operator_status(ctx, name) for name in _INFO_OPERATORS},
    }


def messages(ctx: Ctx, payload: dict) -> dict:
    limit = _limit(payload, 100)
    return {
        "available": False,
        "reason": "Blender does not expose the Info editor report list as stable RNA",
        "limit": limit,
        "messages": [],
    }


COMMANDS = [
    Command("info.report", report, mutates=False),
    Command("info.messages", messages, mutates=False),
]
