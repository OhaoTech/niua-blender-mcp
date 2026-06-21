"""Spreadsheet GUI-parity handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError

_DOMAIN_ALIASES = {
    "": "POINT",
    "VERT": "POINT",
    "VERTEX": "POINT",
    "VERTICES": "POINT",
    "POINTS": "POINT",
    "POINT": "POINT",
    "EDGE": "EDGE",
    "EDGES": "EDGE",
    "FACE": "FACE",
    "FACES": "FACE",
    "POLYGON": "FACE",
    "POLYGONS": "FACE",
    "CORNER": "CORNER",
    "CORNERS": "CORNER",
    "LOOP": "CORNER",
    "LOOPS": "CORNER",
}

_BUILTIN_COLUMNS = {
    "POINT": [
        {"name": "index", "data_type": "INT", "source": "builtin"},
        {"name": "position", "data_type": "FLOAT_VECTOR", "source": "builtin"},
    ],
    "EDGE": [
        {"name": "index", "data_type": "INT", "source": "builtin"},
        {"name": "vertices", "data_type": "INT32_2D", "source": "builtin"},
    ],
    "FACE": [
        {"name": "index", "data_type": "INT", "source": "builtin"},
        {"name": "vertices", "data_type": "INT_ARRAY", "source": "builtin"},
        {"name": "material_index", "data_type": "INT", "source": "builtin"},
        {"name": "loop_start", "data_type": "INT", "source": "builtin"},
        {"name": "loop_total", "data_type": "INT", "source": "builtin"},
    ],
    "CORNER": [
        {"name": "index", "data_type": "INT", "source": "builtin"},
        {"name": "vertex_index", "data_type": "INT", "source": "builtin"},
        {"name": "edge_index", "data_type": "INT", "source": "builtin"},
    ],
}


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


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_list") and callable(value.to_list):
        return [_json_value(item) for item in value.to_list()]
    if hasattr(value, "to_tuple") and callable(value.to_tuple):
        return [_json_value(item) for item in value.to_tuple()]
    try:
        return [_json_value(item) for item in value]
    except TypeError:
        return str(value)


def _domain(payload: dict) -> str:
    raw = payload.get("component", "")
    if raw is None:
        raw = ""
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "component must be a string")
    domain = _DOMAIN_ALIASES.get(raw.strip().upper())
    if domain is None:
        raise BridgeError(INVALID_PARAMS, "component must be POINT, EDGE, FACE, or CORNER")
    return domain


def _limit(payload: dict, key: str, default: int) -> int:
    raw = payload.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise BridgeError(INVALID_PARAMS, f"{key} must be an integer") from exc
    if value < 0:
        raise BridgeError(INVALID_PARAMS, f"{key} must be >= 0")
    return value


def _target_object(ctx: Ctx, payload: dict) -> Any | None:
    obj_name = payload.get("object", "")
    if obj_name is None:
        obj_name = ""
    if not isinstance(obj_name, str):
        raise BridgeError(INVALID_PARAMS, "object must be a string")
    if obj_name:
        return ctx.get_object(obj_name)
    bpy_ctx = getattr(ctx.bpy, "context", None)
    return getattr(bpy_ctx, "object", None) or getattr(bpy_ctx, "active_object", None)


def _space_record(window_index: int, window: Any, area_index: int, area: Any) -> dict[str, Any]:
    screen = getattr(window, "screen", None)
    workspace = getattr(window, "workspace", None)
    space = getattr(getattr(area, "spaces", None), "active", None)
    record: dict[str, Any] = {
        "window_index": window_index,
        "screen": _name(screen),
        "workspace": _name(workspace),
        "area_index": area_index,
        "type": "SPREADSHEET",
        "region_count": len(_items(getattr(area, "regions", []))),
    }
    if space is not None:
        for prop in (
            "show_internal_attributes",
            "use_filter",
            "show_only_selected",
            "is_pinned",
            "geometry_component_type",
            "attribute_domain",
            "object_eval_state",
        ):
            if hasattr(space, prop):
                record[prop] = _json_value(getattr(space, prop))
        record["table_count"] = len(_items(getattr(space, "tables", [])))
        record["row_filter_count"] = len(_items(getattr(space, "row_filters", [])))
    return record


def _spaces(ctx: Ctx) -> list[dict[str, Any]]:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    wm = getattr(bpy_ctx, "window_manager", None)
    records: list[dict[str, Any]] = []
    for window_index, window in enumerate(_items(getattr(wm, "windows", []))):
        screen = getattr(window, "screen", None)
        for area_index, area in enumerate(_items(getattr(screen, "areas", []))):
            if str(getattr(area, "type", "") or "") == "SPREADSHEET":
                records.append(_space_record(window_index, window, area_index, area))
    return records


def _attributes(data: Any, domain: str) -> list[Any]:
    attrs = []
    for attr in _items(getattr(data, "attributes", [])):
        if str(getattr(attr, "domain", "") or "").upper() == domain:
            attrs.append(attr)
    return attrs


def _row_count(obj: Any | None, domain: str) -> int:
    if obj is None:
        return 0
    data = getattr(obj, "data", None)
    if data is None:
        return 0
    if domain == "POINT":
        return len(_items(getattr(data, "vertices", [])) or _items(getattr(data, "points", [])))
    if domain == "EDGE":
        return len(_items(getattr(data, "edges", [])))
    if domain == "FACE":
        return len(_items(getattr(data, "polygons", [])))
    if domain == "CORNER":
        return len(_items(getattr(data, "loops", [])))
    return 0


def _attr_value(attr: Any, index: int) -> Any:
    data = _items(getattr(attr, "data", []))
    if index >= len(data):
        return None
    item = data[index]
    for field in ("value", "vector", "color", "color_srgb", "quaternion"):
        if hasattr(item, field):
            return _json_value(getattr(item, field))
    return None


def _columns(obj: Any | None, domain: str) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = [
        {**column, "domain": domain, "internal": False} for column in _BUILTIN_COLUMNS[domain]
    ]
    seen = {column["name"] for column in columns}
    data = getattr(obj, "data", None) if obj is not None else None
    for attr in _attributes(data, domain) if data is not None else []:
        name = str(getattr(attr, "name", "") or "")
        if not name or name in seen:
            continue
        columns.append(
            {
                "name": name,
                "domain": domain,
                "data_type": str(getattr(attr, "data_type", "") or ""),
                "source": "attribute",
                "internal": name.startswith("."),
            }
        )
        seen.add(name)
    return columns


def _builtin_value(data: Any, domain: str, name: str, index: int) -> Any:
    if name == "index":
        return index
    if domain == "POINT" and name == "position":
        points = _items(getattr(data, "vertices", [])) or _items(getattr(data, "points", []))
        point = points[index]
        return _json_value(getattr(point, "co", None))
    if domain == "EDGE" and name == "vertices":
        edge = _items(getattr(data, "edges", []))[index]
        return _json_value(getattr(edge, "vertices", []))
    if domain == "FACE":
        face = _items(getattr(data, "polygons", []))[index]
        if name == "vertices":
            return _json_value(getattr(face, "vertices", []))
        return _json_value(getattr(face, name, None))
    if domain == "CORNER":
        corner = _items(getattr(data, "loops", []))[index]
        return _json_value(getattr(corner, name, None))
    return None


def _rows(obj: Any | None, domain: str, offset: int, limit: int) -> list[dict[str, Any]]:
    if obj is None:
        return []
    data = getattr(obj, "data", None)
    if data is None:
        return []
    total = _row_count(obj, domain)
    stop = min(total, offset + limit)
    attr_by_name = {str(getattr(attr, "name", "") or ""): attr for attr in _attributes(data, domain)}
    rows: list[dict[str, Any]] = []
    for index in range(min(offset, total), stop):
        row: dict[str, Any] = {}
        for column in _columns(obj, domain):
            name = column["name"]
            if column["source"] == "builtin":
                row[name] = _builtin_value(data, domain, name, index)
            else:
                row[name] = _attr_value(attr_by_name[name], index)
        rows.append(row)
    return rows


def report(ctx: Ctx, payload: dict) -> dict:
    domain = _domain(payload)
    obj = _target_object(ctx, payload)
    cols = _columns(obj, domain)
    spaces = _spaces(ctx)
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "area_count": len(spaces),
        "spaces": spaces,
        "object": _name(obj),
        "object_type": str(getattr(obj, "type", "") or "") if obj is not None else None,
        "component": domain,
        "supported_components": list(_BUILTIN_COLUMNS),
        "row_count": _row_count(obj, domain),
        "column_count": len(cols),
        "columns": cols,
    }


def columns(ctx: Ctx, payload: dict) -> dict:
    domain = _domain(payload)
    obj = _target_object(ctx, payload)
    cols = _columns(obj, domain)
    return {
        "object": _name(obj),
        "object_type": str(getattr(obj, "type", "") or "") if obj is not None else None,
        "component": domain,
        "column_count": len(cols),
        "columns": cols,
    }


def rows(ctx: Ctx, payload: dict) -> dict:
    domain = _domain(payload)
    obj = _target_object(ctx, payload)
    offset = _limit(payload, "offset", 0)
    limit = _limit(payload, "limit", 100)
    total = _row_count(obj, domain)
    page = _rows(obj, domain, offset, limit)
    return {
        "object": _name(obj),
        "object_type": str(getattr(obj, "type", "") or "") if obj is not None else None,
        "component": domain,
        "total": total,
        "offset": offset,
        "limit": limit,
        "count": len(page),
        "rows": page,
    }


COMMANDS = [
    Command("spreadsheet.report", report, mutates=False),
    Command("spreadsheet.columns", columns, mutates=False),
    Command("spreadsheet.rows", rows, mutates=False),
]
