"""RNA introspection: let the agent discover Blender's live API.

`rna.describe` reads operator and data-type metadata straight from the running
Blender via RNA, so the agent can learn any operator's parameters or any type's
properties on demand, without us hand-writing a tool for it.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, BridgeError


def _props(rna: Any) -> list[dict]:
    out: list[dict] = []
    for p in getattr(rna, "properties", []):
        ident = getattr(p, "identifier", "")
        if ident == "rna_type":
            continue
        entry: dict[str, Any] = {
            "id": ident,
            "type": getattr(p, "type", ""),
            "name": getattr(p, "name", ""),
            "description": getattr(p, "description", ""),
        }
        if getattr(p, "type", "") == "ENUM":
            entry["enum"] = [e.identifier for e in getattr(p, "enum_items", [])]
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


COMMANDS = [Command("rna.describe", rna_describe, mutates=False)]
