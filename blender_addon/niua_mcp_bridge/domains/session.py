"""Session domain handlers: checkpoint / revert / list_checkpoints.

The critique loop's safe-iterate primitive. The agent can ``session.checkpoint`` an
object, try an edit (mesh/sculpt/modifier/...), judge the result with ``feedback.critique``,
and ``session.revert`` if the edit made things worse -- without depending on Blender's
fragile, human-shared undo stack. The snapshot store lives in ``..core.session`` so it is
importable and testable on its own; handlers stay tiny.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..core import session as store
from ..dispatch import Command
from ..errors import NOT_FOUND, PRECONDITION, BridgeError


def _resolve_object(ctx: Ctx, payload: dict) -> Any:
    """Return the target object (named, else active); fail cleanly otherwise."""
    name = payload.get("object")
    if isinstance(name, str) and name:
        return ctx.get_object(name)
    view_layer = getattr(ctx.bpy.context, "view_layer", None)
    obj = getattr(getattr(view_layer, "objects", None), "active", None)
    if obj is None:
        obj = getattr(ctx.bpy.context, "object", None)
    if obj is None:
        raise BridgeError(PRECONDITION, "no active object; pass 'object'")
    return obj


def checkpoint(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    label = payload.get("label")
    label = label if isinstance(label, str) and label else None
    return store.checkpoint(obj, label=label)


def revert(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    label = payload.get("label")
    label = label if isinstance(label, str) and label else None
    snapshot = store.get_snapshot(obj.name, label=label)
    if snapshot is None:
        raise BridgeError(
            NOT_FOUND,
            f"no checkpoint for {obj.name}" + (f" with label {label}" if label else ""),
            {"object": obj.name, "label": label},
        )
    store.restore(obj, snapshot)
    data = obj.data
    return {
        "object": obj.name,
        "label": snapshot["label"],
        "vertices": len(list(getattr(data, "vertices", []) or [])),
        "faces": len(list(getattr(data, "polygons", []) or [])),
    }


def list_checkpoints(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("object")
    name = name if isinstance(name, str) and name else None
    return {"checkpoints": store.list_checkpoints(name)}


COMMANDS = [
    Command("session.checkpoint", checkpoint, mutates=False),
    Command("session.revert", revert, mutates=True),
    Command("session.list_checkpoints", list_checkpoints, mutates=False),
]
