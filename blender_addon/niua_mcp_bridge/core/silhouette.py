"""Silhouette eye: render the object as a flat, unlit fill so FORM/proportion read cleanly.

Renders through ``core.capture._render_viewport`` (drives the live 3D viewport, then
captures it -- see docs/reports/capture-multiangle-bug.md "RESOLUTION 2"), so (like the
topology overlay) we assign a flat EMISSION material and render under MATERIAL shading,
then restore the object exactly.
"""
from __future__ import annotations

import base64
import os
import tempfile
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


def render_preservation_views(
    bpy: Any, obj_name: str | None, *, frame: dict | None = None, views=("front", "right", "top"), res: int = 256
) -> dict:
    """Fixed-frame ORTHO alpha silhouettes for the preservation metric (validated live).

    Robust + fail-closed vs the RGB-luma/view_selected ``render_silhouette``:
      * ``film_transparent=True`` + RGBA -> threshold ALPHA (world/lighting/AgX invariant),
      * hidden ortho camera framed ONCE from ``frame`` (the stored intake bbox), never view_selected,
      * ortho-only views, so no perspective foreshortening noise,
      * isolates the subject by snapshotting+hiding every other object's ``hide_render`` (restored).

    Returns ``{available, res, frame:{center,size}, measured:{center,size}, images:[{view,data}]}``
    or ``{available:False, reason}`` on any failure (headless / no GL). No exception escapes -- this
    cannot be exercised under fake-bpy (no GL); it is validated by the live acceptance pass.
    """
    from . import capture as cap

    try:
        center, size = cap.scene_bbox(bpy, obj_name)
        used = frame or {"center": center, "size": size}
        scene = bpy.context.scene
        render = scene.render
        cam = cap._ensure_capture_camera(bpy)
        subject = bpy.data.objects.get(obj_name)
        if subject is None:
            return {"available": False, "reason": f"object not found: {obj_name}"}

        prev = {
            "camera": scene.camera,
            "engine": getattr(render, "engine", None),
            "x": render.resolution_x, "y": render.resolution_y, "pct": render.resolution_percentage,
            "filepath": render.filepath, "fmt": render.image_settings.file_format,
            "color_mode": render.image_settings.color_mode,
            "film_transparent": getattr(render, "film_transparent", None),
        }
        hidden = [(o, o.hide_render) for o in scene.objects]
        path = os.path.join(tempfile.gettempdir(), "niua_preservation.png")
        images: list[dict] = []
        try:
            for o in scene.objects:
                o.hide_render = (o is not subject)
            scene.camera = cam
            render.resolution_x = render.resolution_y = int(res)
            render.resolution_percentage = 100
            render.image_settings.file_format = "PNG"
            render.image_settings.color_mode = "RGBA"
            render.film_transparent = True
            render.filepath = path
            cap._configure_engine(bpy, scene, "MATERIAL")
            for view in views:
                cap._apply_frame(cam, cap.view_camera(used["center"], used["size"], view))
                bpy.ops.render.opengl(write_still=True, view_context=False)
                with open(path, "rb") as fh:
                    images.append({"view": view, "data": base64.b64encode(fh.read()).decode("ascii")})
        finally:
            for o, was in hidden:
                o.hide_render = was
            scene.camera = prev["camera"]
            if prev["engine"] is not None:
                try:
                    render.engine = prev["engine"]
                except Exception:  # noqa: BLE001
                    pass
            render.resolution_x, render.resolution_y = prev["x"], prev["y"]
            render.resolution_percentage = prev["pct"]
            render.filepath, render.image_settings.file_format = prev["filepath"], prev["fmt"]
            render.image_settings.color_mode = prev["color_mode"]
            if prev["film_transparent"] is not None:
                render.film_transparent = prev["film_transparent"]
        return {"available": True, "res": int(res), "frame": used,
                "measured": {"center": center, "size": size}, "images": images}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}


def render_fidelity_views(
    bpy: Any, obj_name: str, *, frame: dict | None = None, views=("front", "right", "top"), res: int = 256
) -> dict:
    """Fixed-frame EEVEE shaded renders (neutral clay + one fixed sun) for the surface-fidelity
    metric. Isolates the subject, applies a temporary clay material + smooth shading so the shaded
    luminance reflects SURFACE detail (and any baked normal map), renders RGBA (alpha = mask), then
    restores every touched piece of state. Degrades to {available:false} headless. LIVE-validated.
    """
    from . import capture as cap
    import base64, os, tempfile

    subject = bpy.data.objects.get(obj_name)
    if subject is None or getattr(subject, "type", None) != "MESH":
        return {"available": False, "reason": f"object not a mesh: {obj_name}"}
    try:
        center, size = cap.scene_bbox(bpy, obj_name)
        used = frame or {"center": center, "size": size}
        scene = bpy.context.scene
        render = scene.render
        cam = cap._ensure_capture_camera(bpy)

        prev = {
            "camera": scene.camera, "engine": getattr(render, "engine", None),
            "x": render.resolution_x, "y": render.resolution_y, "pct": render.resolution_percentage,
            "filepath": render.filepath, "fmt": render.image_settings.file_format,
            "color_mode": render.image_settings.color_mode,
            "film_transparent": getattr(render, "film_transparent", None),
        }
        hidden = [(o, o.hide_render) for o in scene.objects]
        prev_smooth = [p.use_smooth for p in subject.data.polygons]
        path = os.path.join(tempfile.gettempdir(), "niua_fidelity.png")
        images: list[dict] = []
        # Datablock handles must be defined before the inner try so the finally block can
        # always test them -- creating them (or setting their properties) can itself raise,
        # and the finally must then remove whatever WAS created so nothing orphans across
        # the live render loop (else niua_fidelity_clay.001/.002... pile up per asset).
        clay = None
        sun_data = None
        sun_obj = None
        added_clay = False
        try:
            clay = bpy.data.materials.new("niua_fidelity_clay")
            clay.use_nodes = True
            bsdf = clay.node_tree.nodes.get("Principled BSDF")
            if bsdf is not None:
                bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1.0)
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = 0.7
            sun_data = bpy.data.lights.new("niua_fidelity_sun", type="SUN")
            sun_data.energy = 3.0
            sun_obj = bpy.data.objects.new("niua_fidelity_sun", sun_data)
            sun_obj.rotation_euler = (0.9, 0.2, 0.5)
            scene.collection.objects.link(sun_obj)
            for o in scene.objects:
                o.hide_render = (o is not subject and o is not sun_obj)
            # temp clay: replace all slots with the clay material (keep normal-map materials?
            # no -- the metric wants surface SHAPE incl. baked normal, so clay replaces albedo but
            # a caller that wants the baked normal applied must have it wired into the object's OWN
            # material. For the intake high-poly there is no normal map; clay is correct. For a
            # baked low-poly, its own material carries the normal -- so DO NOT override slots when
            # the subject already has a material; only add clay when it has none.)
            if not subject.data.materials:
                subject.data.materials.append(clay)
                added_clay = True
            for p in subject.data.polygons:
                p.use_smooth = True
            scene.camera = cam
            try:
                render.engine = "BLENDER_EEVEE_NEXT"
            except Exception:  # noqa: BLE001 - older EEVEE id
                render.engine = "BLENDER_EEVEE"
            render.resolution_x = render.resolution_y = int(res)
            render.resolution_percentage = 100
            render.image_settings.file_format = "PNG"
            render.image_settings.color_mode = "RGBA"
            render.film_transparent = True
            render.filepath = path
            for view in views:
                cap._apply_frame(cam, cap.view_camera(used["center"], used["size"], view))
                bpy.ops.render.render(write_still=True)
                with open(path, "rb") as fh:
                    images.append({"view": view, "data": base64.b64encode(fh.read()).decode("ascii")})
        finally:
            if added_clay and clay is not None:
                subject.data.materials.pop()
            for p, was in zip(subject.data.polygons, prev_smooth):
                p.use_smooth = was
            if sun_obj is not None:
                bpy.data.objects.remove(sun_obj, do_unlink=True)
            if sun_data is not None:
                bpy.data.lights.remove(sun_data)
            if clay is not None:
                bpy.data.materials.remove(clay)
            for o, was in hidden:
                o.hide_render = was
            scene.camera = prev["camera"]
            if prev["engine"] is not None:
                try:
                    render.engine = prev["engine"]
                except Exception:  # noqa: BLE001
                    pass
            render.resolution_x, render.resolution_y = prev["x"], prev["y"]
            render.resolution_percentage = prev["pct"]
            render.filepath, render.image_settings.file_format = prev["filepath"], prev["fmt"]
            render.image_settings.color_mode = prev["color_mode"]
            if prev["film_transparent"] is not None:
                render.film_transparent = prev["film_transparent"]
        return {"available": True, "res": int(res), "frame": used, "images": images}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}
