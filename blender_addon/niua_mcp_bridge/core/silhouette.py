"""Silhouette eye: render the object as a flat, unlit fill so FORM/proportion read cleanly.

Renders through ``core.capture._render_viewport`` (drives the live 3D viewport, then
captures it -- see docs/reports/capture-multiangle-bug.md "RESOLUTION 2"), so (like the
topology overlay) we assign a flat EMISSION material and render under MATERIAL shading,
then restore the object exactly.
"""
from __future__ import annotations

from typing import Any

# Bright flat fill: the object reads as a uniform bright shape against the darker EEVEE world,
# so the silhouette outline and proportion are unambiguous regardless of scene lighting.
FILL_RGBA = (0.86, 0.86, 0.88, 1.0)


def _ensure_fill_material(bpy: Any) -> Any:
    name = "__niua_silhouette_fill"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    emi.inputs["Color"].default_value = FILL_RGBA
    emi.inputs["Strength"].default_value = 1.0
    nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = FILL_RGBA
    return mat


def _active_mesh(bpy: Any) -> Any:
    vl = getattr(getattr(bpy, "context", None), "view_layer", None)
    objs = getattr(vl, "objects", None)
    return getattr(objs, "active", None)


def render_silhouette(bpy: Any, obj_name: str | None, preset: str = "ortho4", res: int = 768) -> dict:
    from . import capture as cap

    try:
        obj = bpy.data.objects.get(obj_name) if obj_name else _active_mesh(bpy)
        if obj is None or getattr(obj, "type", None) != "MESH":
            return {"available": False, "reason": f"not a mesh object: {obj_name}"}
        mesh = obj.data
        orig_mats = [slot.material for slot in getattr(obj, "material_slots", [])]
        orig_index = [p.material_index for p in mesh.polygons]

        if preset == "orbit4":
            specs = [
                ("orbit_%d" % a, {"azimuth_deg": float(a), "elevation_deg": cap.ORBIT_ELEVATION_DEG})
                for a in (0, 90, 180, 270)
            ]
        else:
            names = cap.PRESETS.get(preset, cap.PRESETS["ortho4"])
            specs = [(n, cap._view_render_kwargs(n)) for n in names]

        images: list[dict] = []
        try:
            obj.data.materials.clear()
            obj.data.materials.append(_ensure_fill_material(bpy))
            for p in mesh.polygons:
                p.material_index = 0
            for name, render_kwargs in specs:
                data = cap._render_viewport(bpy, "MATERIAL", res, obj.name, **render_kwargs)
                images.append({"view": name, "mode": "silhouette", "mimeType": "image/png", "encoding": "base64", "data": data})
        finally:
            obj.data.materials.clear()
            for m in orig_mats:
                obj.data.materials.append(m)
            for p, idx in zip(mesh.polygons, orig_index):
                p.material_index = idx

        return {"available": True, "preset": preset, "images": images}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}
