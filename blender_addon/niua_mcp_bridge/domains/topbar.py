"""Topbar GUI-parity handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError


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


def _operator(ctx: Ctx, idname: str) -> Any | None:
    category, _, name = idname.partition(".")
    if not category or not name:
        return None
    try:
        return getattr(getattr(ctx.bpy.ops, category), name)
    except Exception:  # noqa: BLE001
        return None


def _operator_status(op: Any | None) -> dict[str, Any]:
    if op is None:
        return {"available": False, "reason": "operator not found"}
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
    if value <= 0:
        raise BridgeError(INVALID_PARAMS, "limit must be >= 1")
    return value


def _query(payload: dict) -> str:
    raw = payload.get("query", "")
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "query must be a string")
    return raw


def _rna_text(op: Any) -> tuple[str, str]:
    get_rna_type = getattr(op, "get_rna_type", None)
    if not callable(get_rna_type):
        return "", ""
    try:
        rna = get_rna_type()
    except Exception:  # noqa: BLE001
        return "", ""
    name = str(getattr(rna, "bl_label", "") or getattr(rna, "name", "") or "")
    description = str(getattr(rna, "description", "") or "")
    return name, description


def _score(query: str, idname: str, name: str, description: str) -> int:
    if not query:
        return 1
    q = query.lower()
    best = 0
    for weight, field in zip((100, 60, 30), (idname, name, description)):
        value = (field or "").lower()
        if not value:
            continue
        if value == q:
            best = max(best, weight + 5)
        elif value.startswith(q):
            best = max(best, weight + 3)
        elif q in value:
            best = max(best, weight)
    return best


def _iter_operators(ctx: Ctx):
    ops = getattr(ctx.bpy, "ops", None)
    for category in dir(ops):
        if category.startswith("_"):
            continue
        try:
            module = getattr(ops, category)
        except Exception:  # noqa: BLE001
            continue
        for name in dir(module):
            if name.startswith("_"):
                continue
            try:
                op = getattr(module, name)
            except Exception:  # noqa: BLE001
                continue
            is_operator = (
                callable(op)
                or callable(getattr(op, "poll", None))
                or callable(getattr(op, "get_rna_type", None))
            )
            if not is_operator:
                continue
            yield f"{category}.{name}", op


def report(ctx: Ctx, payload: dict) -> dict:
    areas = _areas(ctx, "TOPBAR")
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "workspace": _context_name(ctx, "workspace"),
        "screen": _context_name(ctx, "screen"),
        "scene": _context_name(ctx, "scene"),
        "mode": str(getattr(getattr(ctx.bpy, "context", None), "mode", "") or ""),
        "area_count": len(areas),
        "areas": areas,
        "search_operator": _operator_status(_operator(ctx, "wm.search_operator")),
    }


def command_search(ctx: Ctx, payload: dict) -> dict:
    query = _query(payload)
    limit = _limit(payload, 20)
    scored: list[tuple[int, dict[str, Any]]] = []
    for idname, op in _iter_operators(ctx):
        name, description = _rna_text(op)
        display_name = name or idname
        score = _score(query, idname, display_name, description)
        if not score:
            continue
        record = {
            "idname": idname,
            "name": display_name,
            "description": description,
            **_operator_status(op),
        }
        scored.append((score, record))

    scored.sort(key=lambda item: (-item[0], item[1]["idname"]))
    results = [record for _, record in scored[:limit]]
    return {"query": query, "limit": limit, "result_count": len(results), "results": results}


COMMANDS = [
    Command("topbar.report", report, mutates=False),
    Command("topbar.command_search", command_search, mutates=False),
]
