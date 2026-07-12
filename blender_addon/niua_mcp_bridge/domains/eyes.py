"""Deeper eyes (addon): topology and UV overlay renders.

NOTE (two-layer split, discovered outside the plan's known move list):
``wire_shaded``/``lookdev`` fold ``feedback.quality`` (finishing-layer policy: asset-class
budgets, engine/material/export-profile readiness) into their ``analytics`` field, the
same "capture + policy quality snapshot" shape as ``feedback.critique``. That makes this
module's import of ``finishing_feedback.quality`` a genuine interface->finishing edge not
covered by the plan's known classification list; Task C (boundary enforcement) needs to
either declare this module a policy domain or otherwise resolve the dependency before the
AST import-direction test can pass.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..core.orientation_metrics import orientation_quality
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


def _ensure_orientation_material(bpy: Any) -> Any:
    mat = bpy.data.materials.get("__niua_orientation_backface")
    if mat is None:
        mat = bpy.data.materials.new("__niua_orientation_backface")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    try:
        geom = nt.nodes.new("ShaderNodeNewGeometry")
        front = nt.nodes.new("ShaderNodeRGB")
        front.outputs["Color"].default_value = (0.18, 0.72, 0.48, 1.0)
        back = nt.nodes.new("ShaderNodeRGB")
        back.outputs["Color"].default_value = (0.95, 0.12, 0.18, 1.0)
        mix = nt.nodes.new("ShaderNodeMixRGB")
        nt.links.new(geom.outputs["Backfacing"], mix.inputs["Fac"])
        nt.links.new(front.outputs["Color"], mix.inputs["Color1"])
        nt.links.new(back.outputs["Color"], mix.inputs["Color2"])
        nt.links.new(mix.outputs["Color"], emi.inputs["Color"])
    except Exception:  # noqa: BLE001 - node names drift across Blender versions
        emi.inputs["Color"].default_value = (0.18, 0.72, 0.48, 1.0)
    emi.inputs["Strength"].default_value = 1.0
    nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = (0.18, 0.72, 0.48, 1.0)
    return mat


def _ensure_flat_material(bpy: Any, name: str, rgba: tuple[float, float, float, float]) -> Any:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = rgba
    emi.inputs["Strength"].default_value = 1.0
    nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = rgba
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
        render_kwargs = cap._view_render_kwargs(view)

        try:
            mesh.materials.clear()
            mesh.materials.append(_ensure_checker_material(ctx.bpy))
            for poly in getattr(mesh, "polygons", []):
                poly.material_index = 0
            image = cap._render_viewport(ctx.bpy, "MATERIAL", res, obj.name, **render_kwargs)
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


def orientation(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap

    obj_name = payload.get("object")
    view = str(payload.get("view", "persp"))
    res = int(payload.get("res", 768))
    analytics: dict

    try:
        obj = _resolve_mesh(ctx, obj_name)
        if obj is None:
            return {"available": False, "reason": f"not a mesh object: {obj_name}", "analytics": {}}
        analytics = orientation_quality(obj)

        mesh = obj.data
        orig_mats = [slot.material for slot in getattr(obj, "material_slots", [])]
        orig_index = [p.material_index for p in getattr(mesh, "polygons", [])]
        render_kwargs = cap._view_render_kwargs(view)

        try:
            mesh.materials.clear()
            mesh.materials.append(_ensure_orientation_material(ctx.bpy))
            for poly in getattr(mesh, "polygons", []):
                poly.material_index = 0
            image = cap._render_viewport(ctx.bpy, "MATERIAL", res, obj.name, **render_kwargs)
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
                    "mode": "orientation",
                    "mimeType": "image/png",
                    "encoding": "base64",
                    "data": image,
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc), "analytics": locals().get("analytics", {})}


def wire_shaded(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap
    from .finishing_feedback import quality

    obj_name = payload.get("object")
    view = str(payload.get("view", "persp"))
    res = int(payload.get("res", 768))
    analytics: dict
    try:
        analytics = quality(ctx, {"object": obj_name} if obj_name else {})
    except Exception as exc:  # noqa: BLE001
        analytics = {"available": False, "reason": str(exc)}

    try:
        obj = _resolve_mesh(ctx, obj_name)
        if obj is None:
            return {"available": False, "reason": f"not a mesh object: {obj_name}", "analytics": analytics}

        mesh = obj.data
        orig_mats = [slot.material for slot in getattr(obj, "material_slots", [])]
        orig_index = [p.material_index for p in getattr(mesh, "polygons", [])]
        _, size = cap.scene_bbox(ctx.bpy, obj.name)  # size drives the wireframe thickness
        render_kwargs = cap._view_render_kwargs(view)
        wire_mod = None

        try:
            if not orig_mats:
                mesh.materials.append(_ensure_flat_material(ctx.bpy, "__niua_wire_base", (0.56, 0.60, 0.62, 1.0)))
                for poly in getattr(mesh, "polygons", []):
                    poly.material_index = 0
            wire_slot = len(mesh.materials)
            mesh.materials.append(_ensure_flat_material(ctx.bpy, "__niua_wire_line", (0.01, 0.01, 0.012, 1.0)))
            wire_mod = obj.modifiers.new(name="__niua_wire_shaded", type="WIREFRAME")
            wire_mod.thickness = max(max(size) * 0.008, 1e-4)
            wire_mod.use_replace = False
            wire_mod.use_even_offset = True
            wire_mod.material_offset = wire_slot
            image = cap._render_viewport(ctx.bpy, "MATERIAL", res, obj.name, **render_kwargs)
        finally:
            if wire_mod is not None:
                try:
                    obj.modifiers.remove(wire_mod)
                except Exception:  # noqa: BLE001
                    pass
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
                    "mode": "wire_shaded",
                    "mimeType": "image/png",
                    "encoding": "base64",
                    "data": image,
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc), "analytics": analytics}


def lookdev(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap
    from .finishing_feedback import quality

    obj_name = payload.get("object")
    count = int(payload.get("count", 6))
    res = int(payload.get("res", 768))
    try:
        analytics = quality(ctx, {"object": obj_name} if obj_name else {})
    except Exception as exc:  # noqa: BLE001
        analytics = {"available": False, "reason": str(exc)}
    out = cap.turntable(ctx.bpy, count=count, shading="MATERIAL", res=res, obj_name=obj_name)
    out["analytics"] = analytics
    return out


COMMANDS = [
    Command("feedback.topology", topology, mutates=False),
    Command("feedback.uv", uv_checker, mutates=False),
    Command("feedback.orientation", orientation, mutates=False),
    Command("feedback.wire_shaded", wire_shaded, mutates=False),
    Command("feedback.lookdev", lookdev, mutates=False),
]
