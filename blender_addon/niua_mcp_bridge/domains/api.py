"""API editor/source GUI-parity handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError


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


def _score(query: str, *fields: str) -> int:
    if not query:
        return 1
    q = query.lower()
    best = 0
    for weight, field in zip((100, 60, 30), fields):
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


def _poll(op: Any) -> dict[str, Any]:
    poll = getattr(op, "poll", None)
    try:
        available = bool(poll()) if callable(poll) else True
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    if not available:
        return {"available": False, "reason": "operator poll returned false"}
    return {"available": True}


def _operator_rna(op: Any) -> tuple[str, str]:
    get_rna_type = getattr(op, "get_rna_type", None)
    if not callable(get_rna_type):
        return "", ""
    try:
        rna = get_rna_type()
    except Exception:  # noqa: BLE001
        return "", ""
    label = str(getattr(rna, "bl_label", "") or getattr(rna, "name", "") or "")
    description = str(getattr(rna, "description", "") or "")
    return label, description


def _operators(ctx: Ctx):
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
            label, description = _operator_rna(op)
            yield f"{category}.{name}", category, label, description, op


def _types(ctx: Ctx):
    types_mod = getattr(ctx.bpy, "types", None)
    for name in dir(types_mod):
        if name.startswith("_"):
            continue
        try:
            value = getattr(types_mod, name)
            rna = getattr(value, "bl_rna")
        except Exception:  # noqa: BLE001
            continue
        label = str(getattr(rna, "name", "") or name)
        description = str(getattr(rna, "description", "") or "")
        yield name, label, description


def report(ctx: Ctx, payload: dict) -> dict:
    operator_records = list(_operators(ctx))
    categories = sorted({category for _idname, category, _label, _description, _op in operator_records})
    type_records = list(_types(ctx))
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "version_string": str(getattr(getattr(ctx.bpy, "app", None), "version_string", "") or ""),
        "operator_count": len(operator_records),
        "operator_category_count": len(categories),
        "operator_categories": categories,
        "type_count": len(type_records),
        "source_space": {
            "available": True,
            "reason": "space_api registers Blender editor/operator/type APIs rather than a modal user editor",
        },
    }


def search(ctx: Ctx, payload: dict) -> dict:
    query = _query(payload)
    limit = _limit(payload, 20)
    scored: list[tuple[int, dict[str, Any]]] = []
    for idname, category, label, description, op in _operators(ctx):
        score = _score(query, idname, label, description)
        if score:
            scored.append(
                (
                    score,
                    {
                        "kind": "operator",
                        "idname": idname,
                        "category": category,
                        "label": label,
                        "description": description,
                        **_poll(op),
                    },
                )
            )
    for name, label, description in _types(ctx):
        score = _score(query, name, label, description)
        if score:
            scored.append(
                (
                    score,
                    {
                        "kind": "type",
                        "name": name,
                        "label": label,
                        "description": description,
                    },
                )
            )

    def ident(record: dict[str, Any]) -> str:
        return str(record.get("idname") or record.get("name") or "")

    scored.sort(key=lambda item: (-item[0], ident(item[1])))
    results = [record for _score_value, record in scored[:limit]]
    return {"query": query, "limit": limit, "result_count": len(results), "results": results}


COMMANDS = [
    Command("api.report", report, mutates=False),
    Command("api.search", search, mutates=False),
]
