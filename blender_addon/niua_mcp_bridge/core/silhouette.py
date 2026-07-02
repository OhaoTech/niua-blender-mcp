"""Silhouette eye: render the object as a flat, unlit fill so FORM/proportion read cleanly.

render.opengl(view_context=False) ignores Workbench shading, so (like the topology overlay) we
assign a flat EMISSION material and render through EEVEE, then restore the object exactly.
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
        center, size = cap.scene_bbox(bpy, obj_name)
        cam_obj = cap._ensure_capture_camera(bpy)

        if preset == "orbit4":
            frames = [("orbit_%d" % a, cap.orbit_camera(center, size, a)) for a in (0, 90, 180, 270)]
        else:
            names = cap.PRESETS.get(preset, cap.PRESETS["ortho4"])
            frames = [(n, cap.view_camera(center, size, n)) for n in names]

        images: list[dict] = []
        try:
            obj.data.materials.clear()
            obj.data.materials.append(_ensure_fill_material(bpy))
            for p in mesh.polygons:
                p.material_index = 0
            for name, frame in frames:
                cap._apply_frame(cam_obj, frame)
                data = cap._render_to_b64(bpy, cam_obj, "MATERIAL", res)
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
