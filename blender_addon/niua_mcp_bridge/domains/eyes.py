"""Deeper eyes (addon): topology and UV overlay renders."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..core.uv_metrics import uv_quality
from ..dispatch import Command
from .uv import report as uv_report


def topology(ctx: Ctx, payload: dict) -> dict:
    from ..core import overlay

    obj = payload.get("object")
    view = str(payload.get("view", "persp"))
    res = int(payload.get("res", 768))
    return overlay.topology_overlay(ctx.bpy, obj_name=obj, view=view, res=res)


def _active_mesh(bpy: Any) -> Any:
    view_layer = getattr(getattr(bpy, "context", None), "view_layer", None)
    objects = getattr(view_layer, "objects", None)
    return getattr(objects, "active", None)


def _resolve_mesh(ctx: Ctx, raw_name: Any) -> Any:
    obj = ctx.bpy.data.objects.get(raw_name) if isinstance(raw_name, str) and raw_name else _active_mesh(ctx.bpy)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return None
    return obj


def _ensure_checker_material(bpy: Any) -> Any:
    mat = bpy.data.materials.get("__niua_uv_checker")
    if mat is None:
        mat = bpy.data.materials.new("__niua_uv_checker")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    checker = nt.nodes.new("ShaderNodeTexChecker")
    checker.inputs["Scale"].default_value = 14.0
    checker.inputs["Color1"].default_value = (0.08, 0.10, 0.12, 1.0)
    checker.inputs["Color2"].default_value = (0.96, 0.92, 0.56, 1.0)
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Strength"].default_value = 1.0
    nt.links.new(checker.outputs["Color"], emi.inputs["Color"])
    nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = (0.96, 0.92, 0.56, 1.0)
    return mat


def uv_checker(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap

    obj_name = payload.get("object")
    view = str(payload.get("view", "persp"))
    res = int(payload.get("res", 768))
    texture_size = int(payload.get("texture_size", 1024))
    analytics: dict
    try:
        analytics = uv_report(ctx, {"object": obj_name} if obj_name else {})
    except Exception as exc:  # noqa: BLE001
        analytics = {"available": False, "reason": str(exc)}

    try:
        obj = _resolve_mesh(ctx, obj_name)
        if obj is None:
            return {"available": False, "reason": f"not a mesh object: {obj_name}", "analytics": analytics}
        if analytics.get("available") is not False:
            analytics.update(uv_quality(obj, texture_size=texture_size, island_count=analytics.get("island_count")))

        mesh = obj.data
        orig_mats = [slot.material for slot in getattr(obj, "material_slots", [])]
        orig_index = [p.material_index for p in getattr(mesh, "polygons", [])]
        center, size = cap.scene_bbox(ctx.bpy, obj.name)
        cam_obj = cap._ensure_capture_camera(ctx.bpy)
        cap._apply_frame(cam_obj, cap.view_camera(center, size, view))

        try:
            mesh.materials.clear()
            mesh.materials.append(_ensure_checker_material(ctx.bpy))
            for poly in getattr(mesh, "polygons", []):
                poly.material_index = 0
            image = cap._render_to_b64(ctx.bpy, cam_obj, "MATERIAL", res)
        finally:
            mesh.materials.clear()
            for mat in orig_mats:
                mesh.materials.append(mat)
            for poly, index in zip(getattr(mesh, "polygons", []), orig_index):
                poly.material_index = index

        return {
            "available": True,
            "view": view,
            "analytics": analytics,
            "images": [
                {
                    "view": view,
                    "mode": "checker",
                    "mimeType": "image/png",
                    "encoding": "base64",
                    "data": image,
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc), "analytics": analytics}


COMMANDS = [
    Command("feedback.topology", topology, mutates=False),
    Command("feedback.uv", uv_checker, mutates=False),
]
