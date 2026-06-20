"""Topology overlay: mark defects with real materials instead of viewport overlays.

``render.opengl(view_context=False)`` renders from the capture camera and ignores
viewport overlays. The topology eye therefore assigns temporary materials to mesh
faces, renders, then restores the user's mesh exactly.
"""

from __future__ import annotations

from typing import Any, Iterable


def face_type_groups(polygons: Iterable[Any]) -> dict:
    """Group polygon indices by side count: tris (3), quads (4), ngons (>4)."""
    tris: list[int] = []
    quads: list[int] = []
    ngons: list[int] = []
    for p in polygons:
        sides = len(p.vertices)
        if sides == 3:
            tris.append(p.index)
        elif sides == 4:
            quads.append(p.index)
        elif sides > 4:
            ngons.append(p.index)
    return {"tris": tris, "quads": quads, "ngons": ngons}


QUAD_RGBA = (0.30, 0.30, 0.30, 1.0)
TRI_RGBA = (0.95, 0.55, 0.10, 1.0)
NGON_RGBA = (0.90, 0.10, 0.10, 1.0)


def _ensure_marker_materials(bpy: Any) -> list:
    """Create/reuse marker materials [quad, tri, ngon]."""
    names = ["__niua_topo_quad", "__niua_topo_tri", "__niua_topo_ngon"]
    rgbas = [QUAD_RGBA, TRI_RGBA, NGON_RGBA]
    mats = []
    for name, rgba in zip(names, rgbas):
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
        mat.use_nodes = False
        mat.diffuse_color = rgba
        mats.append(mat)
    return mats


def _active_mesh(bpy: Any) -> Any:
    view_layer = getattr(getattr(bpy, "context", None), "view_layer", None)
    objects = getattr(view_layer, "objects", None)
    return getattr(objects, "active", None)


def topology_overlay(bpy: Any, obj_name: str | None, view: str = "persp", res: int = 768) -> dict:
    """Render face-type and wireframe topology images, degrading gracefully."""
    from . import capture as cap

    try:
        obj = bpy.data.objects.get(obj_name) if obj_name else _active_mesh(bpy)
        if obj is None or getattr(obj, "type", None) != "MESH":
            return {"available": False, "reason": f"not a mesh object: {obj_name}"}
        mesh = obj.data
        groups = face_type_groups(mesh.polygons)

        orig_mats = [slot.material for slot in getattr(obj, "material_slots", [])]
        orig_index = [p.material_index for p in mesh.polygons]
        center, size = cap.scene_bbox(bpy, obj_name)
        cam_obj = cap._ensure_capture_camera(bpy)
        frame = cap.view_camera(center, size, view)
        cap._apply_frame(cam_obj, frame)

        shading = getattr(getattr(bpy.context.scene, "display", None), "shading", None)
        orig_color_type = getattr(shading, "color_type", None)
        try:
            if shading is not None and hasattr(shading, "color_type"):
                shading.color_type = "MATERIAL"
            obj.data.materials.clear()
            for mat in _ensure_marker_materials(bpy):
                obj.data.materials.append(mat)
            for p in mesh.polygons:
                sides = len(p.vertices)
                p.material_index = 0 if sides == 4 else (1 if sides == 3 else 2)
            facetype = cap._render_to_b64(bpy, cam_obj, "SOLID", res)
            wire = cap._render_to_b64(bpy, cam_obj, "WIREFRAME", res)
        finally:
            obj.data.materials.clear()
            for mat in orig_mats:
                obj.data.materials.append(mat)
            for p, idx in zip(mesh.polygons, orig_index):
                p.material_index = idx
            if shading is not None and orig_color_type is not None:
                try:
                    shading.color_type = orig_color_type
                except Exception:  # noqa: BLE001 - restore best-effort only
                    pass

        return {
            "available": True,
            "view": view,
            "groups": {k: len(v) for k, v in groups.items()},
            "images": [
                {
                    "view": view,
                    "mode": "facetype",
                    "mimeType": "image/png",
                    "encoding": "base64",
                    "data": facetype,
                },
                {
                    "view": view,
                    "mode": "wireframe",
                    "mimeType": "image/png",
                    "encoding": "base64",
                    "data": wire,
                },
            ],
        }
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}
