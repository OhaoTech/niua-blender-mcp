"""RNA introspection: let the agent discover Blender's live API.

`rna.describe` reads operator and data-type metadata straight from the running
Blender via RNA, so the agent can learn any operator's parameters or any type's
properties on demand, without us hand-writing a tool for it.

`rna.search` mines the live `bpy.ops` and `bpy.types` for operators/types whose
idname/label/description match a query, ranked by relevance. This gives the agent
uncapped discovery without flooding tools/list with hundreds of static defs.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, BridgeError

# UI/system categories the agent should not be driving generically.
_SKIP_CATEGORIES = frozenset({"wm", "screen", "file", "ui", "console", "preferences"})


def _props(rna: Any) -> list[dict]:
    out: list[dict] = []
    for p in getattr(rna, "properties", []):
        ident = getattr(p, "identifier", "")
        if ident == "rna_type":
            continue
        ptype = getattr(p, "type", "")
        entry: dict[str, Any] = {
            "id": ident,
            "type": ptype,
            "name": getattr(p, "name", ""),
            "description": getattr(p, "description", ""),
        }
        # Operator props are not readonly; type/data props often are. Surface it so the
        # agent knows what it can actually set via rna.set_property.
        if getattr(p, "is_readonly", False):
            entry["readonly"] = True
        if getattr(p, "is_required", False):
            entry["required"] = True
        if ptype == "ENUM":
            entry["enum"] = [e.identifier for e in getattr(p, "enum_items", [])]
        else:
            default = getattr(p, "default", None)
            if default is not None:
                entry["default"] = default
            hard_min = getattr(p, "hard_min", None)
            hard_max = getattr(p, "hard_max", None)
            if hard_min is not None:
                entry["min"] = hard_min
            if hard_max is not None:
                entry["max"] = hard_max
        out.append(entry)
    return out


def rna_describe(ctx: Ctx, payload: dict) -> dict:
    bpy = ctx.bpy
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required, e.g. 'op:mesh.bevel' or 'type:Object'")
    kind, _, ref = path.partition(":")

    if kind == "op":
        category, _, name = ref.partition(".")
        try:
            op = getattr(getattr(bpy.ops, category), name)
            rna = op.get_rna_type()
        except Exception as exc:  # noqa: BLE001
            raise BridgeError(NOT_FOUND, f"operator not found: {ref}", {"error": str(exc)}) from exc
        return {
            "kind": "operator",
            "id": ref,
            "description": getattr(rna, "description", ""),
            "properties": _props(rna),
        }

    if kind == "type":
        try:
            rna = getattr(bpy.types, ref).bl_rna
        except Exception as exc:  # noqa: BLE001
            raise BridgeError(NOT_FOUND, f"type not found: {ref}", {"error": str(exc)}) from exc
        return {
            "kind": "type",
            "id": ref,
            "description": getattr(rna, "description", ""),
            "properties": _props(rna),
        }

    raise BridgeError(INVALID_PARAMS, "path must start with 'op:' or 'type:'")


def _score(query: str, *fields: str) -> int:
    """Rank a candidate by where the query substring appears.

    Higher is better. An exact idname/name match wins, then a prefix match,
    then any substring; the earlier (more identifying) the field, the more it
    weighs. 0 means no match anywhere (caller drops it).
    """
    if not query:
        return 1  # no query: keep everything (still filtered by description/category)
    q = query.lower()
    best = 0
    # fields are passed most-identifying-first; weight them by position.
    for weight, field in zip((100, 60, 30), fields):
        f = (field or "").lower()
        if not f:
            continue
        if f == q:
            best = max(best, weight + 5)
        elif f.startswith(q):
            best = max(best, weight + 3)
        elif q in f:
            best = max(best, weight)
    return best


def _iter_operators(bpy: Any, category_filter: str | None):
    """Yield (idname, category, label, description) for usable operators."""
    ops = bpy.ops
    for cat in dir(ops):
        if cat.startswith("_") or cat in _SKIP_CATEGORIES:
            continue
        if category_filter and cat != category_filter:
            continue
        try:
            module = getattr(ops, cat)
        except Exception:  # noqa: BLE001
            continue
        for name in dir(module):
            if name.startswith("_"):
                continue
            try:
                rna = getattr(module, name).get_rna_type()
            except Exception:  # noqa: BLE001
                continue
            desc = (getattr(rna, "description", "") or "").strip()
            if not desc:
                continue  # require real help text
            label = getattr(rna, "bl_label", "") or getattr(rna, "name", "") or ""
            yield (f"{cat}.{name}", cat, label, desc)


def _iter_types(bpy: Any):
    """Yield (name, description) for documented bpy.types."""
    types_mod = bpy.types
    for tname in dir(types_mod):
        if tname.startswith("_"):
            continue
        try:
            rna = getattr(types_mod, tname).bl_rna
        except Exception:  # noqa: BLE001
            continue
        desc = (getattr(rna, "description", "") or "").strip()
        if not desc:
            continue
        yield (tname, desc)


def rna_search(ctx: Ctx, payload: dict) -> dict:
    bpy = ctx.bpy
    query = payload.get("query", "") or ""
    if not isinstance(query, str):
        raise BridgeError(INVALID_PARAMS, "query must be a string")
    kind = payload.get("kind", "any") or "any"
    if kind not in ("operator", "type", "any"):
        raise BridgeError(INVALID_PARAMS, "kind must be 'operator', 'type', or 'any'")
    category = payload.get("category") or None
    if category is not None and not isinstance(category, str):
        raise BridgeError(INVALID_PARAMS, "category must be a string")
    limit = payload.get("limit", 30)
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise BridgeError(INVALID_PARAMS, "limit must be an integer") from exc
    if limit <= 0:
        limit = 30

    scored: list[tuple[int, dict]] = []

    if kind in ("operator", "any"):
        for idname, cat, label, desc in _iter_operators(bpy, category):
            s = _score(query, idname, label, desc)
            if s:
                scored.append(
                    (s, {"kind": "operator", "idname": idname, "category": cat,
                         "label": label, "description": desc})
                )

    if kind in ("type", "any"):
        for tname, desc in _iter_types(bpy):
            s = _score(query, tname, "", desc)
            if s:
                scored.append((s, {"kind": "type", "name": tname, "description": desc}))

    # Stable, relevance-first ordering; tie-break by identifier for determinism.
    def _ident(rec: dict) -> str:
        return rec.get("idname") or rec.get("name") or ""

    scored.sort(key=lambda item: (-item[0], _ident(item[1])))
    matches = [rec for _, rec in scored[:limit]]
    return {"query": query, "kind": kind, "count": len(matches), "matches": matches}


COMMANDS = [
    Command("rna.describe", rna_describe, mutates=False),
    Command("rna.search", rna_search, mutates=False),
]
