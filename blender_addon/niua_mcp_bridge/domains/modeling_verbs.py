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


def bevel_edges(ctx: Ctx, payload: dict) -> dict:
    obj_name = payload.get("object")
    if not isinstance(obj_name, str) or not obj_name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(obj_name)
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(PRECONDITION, f"object is not a mesh: {obj_name}")

    angle = math.radians(float(payload.get("angle", 30.0)))
    width = float(payload.get("width", 0.02))
    segments = int(payload.get("segments", 2))
    ops = ctx.bpy.ops
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="DESELECT")
        ctx.check_poll(ops.mesh.edges_select_sharp)
        ops.mesh.edges_select_sharp(sharpness=angle)
        ctx.check_poll(ops.mesh.bevel)
        ops.mesh.bevel(offset=width, segments=segments, affect="EDGES")
    return {"object": obj.name, "applied": ["edges_select_sharp", "bevel"], "segments": segments}


def recess_panels(ctx: Ctx, payload: dict) -> dict:
    obj_name = payload.get("object")
    if not isinstance(obj_name, str) or not obj_name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(obj_name)
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(PRECONDITION, f"object is not a mesh: {obj_name}")

    inset = float(payload.get("inset", 0.08))
    depth = float(payload.get("depth", 0.04))
    ops = ctx.bpy.ops
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        ctx.check_poll(ops.mesh.inset)
        ops.mesh.inset(thickness=inset, depth=-depth, use_individual=True)
    return {"object": obj.name, "applied": ["select_all", "inset"], "inset": inset, "depth": depth}


COMMANDS = [
    Command("model.retopo_quads", retopo_quads, mutates=True, feedback="viewport"),
    Command("model.bevel_edges", bevel_edges, mutates=True, feedback="viewport"),
    Command("model.recess_panels", recess_panels, mutates=True, feedback="viewport"),
]
