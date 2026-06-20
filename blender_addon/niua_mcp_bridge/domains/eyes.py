"""Deeper eyes (addon): topology overlay render."""

from __future__ import annotations

from ..context import Ctx
from ..dispatch import Command


def topology(ctx: Ctx, payload: dict) -> dict:
    from ..core import overlay

    obj = payload.get("object")
    view = str(payload.get("view", "persp"))
    res = int(payload.get("res", 768))
    return overlay.topology_overlay(ctx.bpy, obj_name=obj, view=view, res=res)


COMMANDS = [
    Command("feedback.topology", topology, mutates=False),
]
