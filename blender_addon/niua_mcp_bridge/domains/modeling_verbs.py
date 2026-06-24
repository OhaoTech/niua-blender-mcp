"""Seed craft verbs (addon): composite senior modeling operations."""

from __future__ import annotations

import math

from ..context import Ctx
from ..core import craft_workflows
from ..dispatch import Command
from ..errors import INVALID_PARAMS, PRECONDITION, BridgeError


def _mesh_object(ctx: Ctx, payload: dict):
    obj_name = payload.get("object")
    if not isinstance(obj_name, str) or not obj_name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(obj_name)
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(PRECONDITION, f"object is not a mesh: {obj_name}")
    return obj


def _workflow_defaults(workflow_id: str) -> tuple[dict, dict]:
    workflow = craft_workflows.get_workflow(workflow_id)
    return workflow, workflow["default_params"]


def _optional_mesh_op(
    ctx: Ctx, op, name: str, applied: list[str], skipped: list[dict], warnings: list[str]
) -> bool:
    if op is None:
        skipped.append({"operator": name, "reason": "unavailable"})
        warnings.append("mesh.delete_loose was unavailable; inspect for loose generated fragments.")
        return False
    try:
        ctx.check_poll(op)
    except BridgeError:
        skipped.append({"operator": name, "reason": "unavailable"})
        warnings.append("mesh.delete_loose was unavailable; inspect for loose generated fragments.")
        return False
    op()
    applied.append(name.split(".")[-1])
    return True


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


def panel_detail_pass(ctx: Ctx, payload: dict) -> dict:
    obj_name = payload.get("object")
    if not isinstance(obj_name, str) or not obj_name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(obj_name)
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(PRECONDITION, f"object is not a mesh: {obj_name}")

    workflow = craft_workflows.get_workflow("hard_surface.panel_detail_pass")
    defaults = workflow["default_params"]
    inset = float(payload.get("inset", defaults["inset"]))
    depth = float(payload.get("depth", defaults["depth"]))
    angle = float(payload.get("angle", defaults["angle"]))
    width = float(payload.get("width", defaults["width"]))
    segments = int(payload.get("segments", defaults["segments"]))
    face_threshold = float(payload.get("face_threshold", defaults["face_threshold"]))
    angle_radians = math.radians(angle)
    threshold_radians = math.radians(face_threshold)

    ops = ctx.bpy.ops
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        ctx.check_poll(ops.mesh.inset)
        ops.mesh.inset(thickness=inset, depth=-depth, use_individual=True)
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="DESELECT")
        ctx.check_poll(ops.mesh.edges_select_sharp)
        ops.mesh.edges_select_sharp(sharpness=angle_radians)
        ctx.check_poll(ops.mesh.bevel)
        ops.mesh.bevel(offset=width, segments=segments, affect="EDGES")
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        ctx.check_poll(ops.mesh.tris_convert_to_quads)
        ops.mesh.tris_convert_to_quads(
            face_threshold=threshold_radians,
            shape_threshold=threshold_radians,
        )
        ctx.check_poll(ops.mesh.normals_make_consistent)
        ops.mesh.normals_make_consistent()
        ctx.check_poll(ops.mesh.remove_doubles)
        ops.mesh.remove_doubles()

    return {
        "object": obj.name,
        "asset_class": workflow["asset_class"],
        "workflow_id": workflow["id"],
        "applied": [
            "select_all",
            "inset",
            "edges_select_sharp",
            "bevel",
            "tris_convert_to_quads",
            "normals_make_consistent",
            "remove_doubles",
        ],
        "params": {
            "inset": inset,
            "depth": depth,
            "angle": angle,
            "width": width,
            "segments": segments,
            "face_threshold": face_threshold,
        },
        "warnings": [workflow["cautions"][1]],
    }


def generated_cleanup_pass(ctx: Ctx, payload: dict) -> dict:
    obj = _mesh_object(ctx, payload)
    workflow, defaults = _workflow_defaults("generated_cleanup.rebuild_noisy_mesh")
    face_threshold = float(payload.get("face_threshold", defaults["face_threshold"]))
    merge_distance = float(payload.get("merge_distance", defaults["merge_distance"]))
    threshold_radians = math.radians(face_threshold)
    applied: list[str] = []
    skipped: list[dict] = []
    warnings = [workflow["cautions"][0]]
    ops = ctx.bpy.ops

    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        applied.append("select_all")
        ctx.check_poll(ops.mesh.normals_make_consistent)
        ops.mesh.normals_make_consistent()
        applied.append("normals_make_consistent")
        ctx.check_poll(ops.mesh.remove_doubles)
        ops.mesh.remove_doubles(threshold=merge_distance)
        applied.append("remove_doubles")
        _optional_mesh_op(
            ctx,
            getattr(ops.mesh, "delete_loose", None),
            "mesh.delete_loose",
            applied,
            skipped,
            warnings,
        )
        ctx.check_poll(ops.mesh.tris_convert_to_quads)
        ops.mesh.tris_convert_to_quads(
            face_threshold=threshold_radians,
            shape_threshold=threshold_radians,
        )
        applied.append("tris_convert_to_quads")

    return {
        "object": obj.name,
        "asset_class": workflow["asset_class"],
        "workflow_id": workflow["id"],
        "applied": applied,
        "skipped": skipped,
        "params": {"face_threshold": face_threshold, "merge_distance": merge_distance},
        "warnings": warnings,
        "postcheck_recommended": ["feedback.topology", "pipeline.gate_check"],
    }


def organic_retopo_prep(ctx: Ctx, payload: dict) -> dict:
    obj = _mesh_object(ctx, payload)
    workflow, defaults = _workflow_defaults("organic.silhouette_retopo_prep")
    face_threshold = float(payload.get("face_threshold", defaults["face_threshold"]))
    merge_distance = float(payload.get("merge_distance", defaults["merge_distance"]))
    threshold_radians = math.radians(face_threshold)
    applied: list[str] = []
    ops = ctx.bpy.ops

    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT")
        applied.append("select_all")
        ctx.check_poll(ops.mesh.normals_make_consistent)
        ops.mesh.normals_make_consistent()
        applied.append("normals_make_consistent")
        ctx.check_poll(ops.mesh.remove_doubles)
        ops.mesh.remove_doubles(threshold=merge_distance)
        applied.append("remove_doubles")
        ctx.check_poll(ops.mesh.tris_convert_to_quads)
        ops.mesh.tris_convert_to_quads(
            face_threshold=threshold_radians,
            shape_threshold=threshold_radians,
        )
        applied.append("tris_convert_to_quads")

    return {
        "object": obj.name,
        "asset_class": workflow["asset_class"],
        "workflow_id": workflow["id"],
        "applied": applied,
        "skipped": [],
        "params": {"face_threshold": face_threshold, "merge_distance": merge_distance},
        "warnings": [workflow["cautions"][0]],
        "postcheck_recommended": ["feedback.topology", "pipeline.gate_check"],
    }


COMMANDS = [
    Command("model.retopo_quads", retopo_quads, mutates=True, feedback="viewport"),
    Command("model.bevel_edges", bevel_edges, mutates=True, feedback="viewport"),
    Command("model.recess_panels", recess_panels, mutates=True, feedback="viewport"),
    Command("hard_surface.panel_detail_pass", panel_detail_pass, mutates=True, feedback="viewport"),
    Command("model.generated_cleanup_pass", generated_cleanup_pass, mutates=True, feedback="viewport"),
    Command("model.organic_retopo_prep", organic_retopo_prep, mutates=True, feedback="viewport"),
]
