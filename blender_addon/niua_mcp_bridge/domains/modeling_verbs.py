"""Seed craft verbs (addon): composite senior modeling operations."""

from __future__ import annotations

import math

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, PRECONDITION, BridgeError


def retopo_quads(ctx: Ctx, payload: dict) -> dict:
    obj_name = payload.get("object")
    if not isinstance(obj_name, str) or not obj_name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(obj_name)
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(PRECONDITION, f"object is not a mesh: {obj_name}")

    threshold = math.radians(float(payload.get("face_threshold", 40.0)))
    ops = ctx.bpy.ops
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        ctx.check_poll(ops.mesh.tris_convert_to_quads)
        ops.mesh.tris_convert_to_quads(face_threshold=threshold, shape_threshold=threshold)
        ctx.check_poll(ops.mesh.normals_make_consistent)
        ops.mesh.normals_make_consistent()
        ctx.check_poll(ops.mesh.remove_doubles)
        ops.mesh.remove_doubles()
    return {
        "object": obj.name,
        "applied": ["tris_convert_to_quads", "normals_make_consistent", "remove_doubles"],
    }


COMMANDS = [
    Command("model.retopo_quads", retopo_quads, mutates=True, feedback="viewport"),
]
