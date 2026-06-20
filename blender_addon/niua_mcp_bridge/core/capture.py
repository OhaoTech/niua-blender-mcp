"""The rendering engine behind the feedback subsystem -- the agent's eyes.

The anti-blob principle from the project's origin: to judge *form* you must see it from
several angles, not one lucky shot. This module owns a dedicated, hidden capture camera
so the user's viewport and view never move, computes faithful framing for named views
(front/back/left/right/top/bottom/persp) around an object's (or the whole scene's) world
bounding box, and renders via ``bpy.ops.render.opengl`` (fast workbench / EEVEE).

Two layers:

* **Pure-Python framing math** (``bbox_*`` / ``view_camera`` / ``orbit_camera``) takes a
  bbox center + size and returns a camera ``location``, ``rotation_euler`` and (for
  orthographic views) an ``ortho_scale``. No ``bpy`` involved, so it is unit-testable
  against a fake bpy / plain numbers.
* **bpy-bound rendering** (``render`` / ``capture_views`` / ``turntable``) which creates
  or reuses the hidden camera, applies a frame, sets the engine + shading, renders to a
  temp PNG and returns base64. Every failure (headless, no GPU, no display) degrades to
  ``{"available": False, "reason": ...}`` exactly like the original ``feedback.capture``.

``bpy`` is imported lazily inside the bpy-bound functions, never at module top, so the
framing math stays importable under fake-bpy unit tests.
"""

from __future__ import annotations

import base64
import math
import os
import tempfile
from typing import Any, Iterable

CAPTURE_CAM = "__niua_capture_cam"

#: Engines/shading the renderer understands. SOLID/WIREFRAME -> Workbench, the rest EEVEE.
WORKBENCH_SHADING = {"SOLID", "WIREFRAME"}
EEVEE_SHADING = {"MATERIAL", "RENDERED"}

#: Named orthographic views: unit direction the camera sits along, looking back at center.
#: rotation_euler aims the camera's local -Z at the bbox center along that direction.
_VIEWS: dict[str, dict[str, Any]] = {
    # name:   direction the camera is offset toward,   euler (rad) so -Z faces center
    "front":  {"dir": (0.0, -1.0, 0.0), "rot": (math.pi / 2, 0.0, 0.0), "ortho": True},
    "back":   {"dir": (0.0, 1.0, 0.0), "rot": (math.pi / 2, 0.0, math.pi), "ortho": True},
    "right":  {"dir": (1.0, 0.0, 0.0), "rot": (math.pi / 2, 0.0, math.pi / 2), "ortho": True},
    "left":   {"dir": (-1.0, 0.0, 0.0), "rot": (math.pi / 2, 0.0, -math.pi / 2), "ortho": True},
    "top":    {"dir": (0.0, 0.0, 1.0), "rot": (0.0, 0.0, 0.0), "ortho": True},
    "bottom": {"dir": (0.0, 0.0, -1.0), "rot": (math.pi, 0.0, 0.0), "ortho": True},
    # 3/4 perspective: classic Blender-ish front-right-top look.
    "persp":  {"dir": (1.0, -1.0, 0.7), "rot": (math.radians(60.0), 0.0, math.radians(45.0)), "ortho": False},
}

#: Multi-view presets for capture_views.
PRESETS: dict[str, list[str]] = {
    "ortho4": ["front", "right", "top", "persp"],
    "ortho6": ["front", "back", "left", "right", "top", "bottom"],
    "orbit4": ["persp"],  # overridden below to four orbit angles by capture_views
}


# --------------------------------------------------------------------------------------
# Pure-Python framing math (unit-testable, no bpy)
# --------------------------------------------------------------------------------------

def bbox_center_size(corners: Iterable[Iterable[float]]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Given world-space bbox corners (any count >= 1), return (center, size) triples."""
    xs, ys, zs = [], [], []
    for c in corners:
        x, y, z = c[0], c[1], c[2]
        xs.append(x); ys.append(y); zs.append(z)
    if not xs:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    lo = (min(xs), min(ys), min(zs))
    hi = (max(xs), max(ys), max(zs))
    center = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
    size = tuple(hi[i] - lo[i] for i in range(3))
    return center, size  # type: ignore[return-value]


def _norm(v: tuple[float, float, float]) -> tuple[float, float, float]:
    mag = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def fit_distance(size: tuple[float, float, float], margin: float = 1.3) -> float:
    """A conservative perspective stand-off distance for a bbox of the given size."""
    radius = max(math.sqrt(sum(c * c for c in size)) / 2.0, 1e-4)
    return radius * 2.2 * margin


def ortho_scale(size: tuple[float, float, float], view: str, margin: float = 1.15) -> float:
    """Orthographic scale (the larger on-screen extent) for a named axis-aligned view."""
    sx, sy, sz = size
    # The two extents perpendicular to the viewing axis.
    if view in ("front", "back"):
        extent = max(sx, sz)
    elif view in ("left", "right"):
        extent = max(sy, sz)
    elif view in ("top", "bottom"):
        extent = max(sx, sy)
    else:
        extent = max(sx, sy, sz)
    return max(extent, 1e-4) * margin


def view_camera(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    view: str,
    margin: float = 1.3,
) -> dict[str, Any]:
    """Camera placement for a named view of a bbox.

    Returns ``{location, rotation_euler, type ('ORTHO'|'PERSP'), ortho_scale?}``. The
    camera sits along the view direction at a fitted distance and aims its local -Z back
    at ``center``. Orthographic for the six axis views, perspective for ``persp``.
    """
    spec = _VIEWS.get(view)
    if spec is None:
        raise ValueError(f"unknown view: {view}")
    direction = _norm(spec["dir"])
    dist = fit_distance(size, margin)
    location = tuple(center[i] + direction[i] * dist for i in range(3))
    out: dict[str, Any] = {
        "location": location,
        "rotation_euler": tuple(spec["rot"]),
        "type": "ORTHO" if spec["ortho"] else "PERSP",
    }
    if spec["ortho"]:
        out["ortho_scale"] = ortho_scale(size, view, margin=1.15)
    return out


def orbit_camera(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    angle_deg: float,
    elevation_deg: float = 25.0,
    margin: float = 1.3,
) -> dict[str, Any]:
    """Perspective camera orbiting the bbox at ``angle_deg`` azimuth + ``elevation_deg``.

    angle 0 looks from -Y (front); azimuth increases counter-clockwise (toward +X). The
    camera aims its -Z back at center: yaw = angle, pitch = 90deg - elevation.
    """
    az = math.radians(angle_deg)
    el = math.radians(elevation_deg)
    dist = fit_distance(size, margin)
    # Horizontal offset on the XY plane (az measured from -Y toward +X), plus elevation.
    horiz = math.cos(el)
    dx = math.sin(az) * horiz
    dy = -math.cos(az) * horiz
    dz = math.sin(el)
    location = (center[0] + dx * dist, center[1] + dy * dist, center[2] + dz * dist)
    rotation_euler = (math.pi / 2 - el, 0.0, az)
    return {"location": location, "rotation_euler": rotation_euler, "type": "PERSP"}


# --------------------------------------------------------------------------------------
# bpy-bound rendering (degrades gracefully headless / no GPU)
# --------------------------------------------------------------------------------------

def _world_bbox_corners(bpy: Any, obj: Any) -> list[tuple[float, float, float]]:
    """World-space 8 bbox corners of an object (matrix_world @ local bound_box)."""
    mw = obj.matrix_world
    corners = []
    for local in obj.bound_box:
        corners.append(tuple(mw @ _Vector(bpy, local)))
    return corners


def _Vector(bpy: Any, seq) -> Any:
    """mathutils.Vector for real matrix math; plain tuple under fake-bpy tests.

    mathutils is a TOP-LEVEL module in Blender (``import mathutils``), NOT an attribute
    of bpy. Using a Vector matters because ``matrix_world @ tuple`` is illegal in Blender
    (only ``Matrix @ Vector`` works); the tuple fallback is only ever hit in unit tests
    that don't perform real matrix multiplication.
    """
    try:
        import mathutils  # noqa: PLC0415 - real Blender only

        return mathutils.Vector(seq)
    except Exception:  # noqa: BLE001
        return tuple(seq)


def scene_bbox(bpy: Any, obj_name: str | None) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Compute (center, size) for one object or, when ``obj_name`` is None, the scene."""
    if obj_name:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            raise ValueError(f"object not found: {obj_name}")
        return bbox_center_size(_world_bbox_corners(bpy, obj))
    corners: list[tuple[float, float, float]] = []
    for obj in bpy.context.scene.objects:
        if getattr(obj, "type", None) in ("MESH", "CURVE", "SURFACE", "META", "FONT"):
            try:
                corners.extend(_world_bbox_corners(bpy, obj))
            except Exception:  # noqa: BLE001 - skip objects without a usable bbox
                continue
    if not corners:
        return (0.0, 0.0, 0.0), (2.0, 2.0, 2.0)
    return bbox_center_size(corners)


def _ensure_capture_camera(bpy: Any) -> Any:
    """Create or reuse the hidden capture camera. Never touches the user's cameras."""
    cam_obj = bpy.data.objects.get(CAPTURE_CAM)
    if cam_obj is None:
        cam_data = bpy.data.cameras.new(CAPTURE_CAM)
        cam_obj = bpy.data.objects.new(CAPTURE_CAM, cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.hide_viewport = True
    cam_obj.hide_render = False
    return cam_obj


def _apply_frame(cam_obj: Any, frame: dict[str, Any]) -> None:
    cam_obj.location = frame["location"]
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = frame["rotation_euler"]
    cam = cam_obj.data
    if frame["type"] == "ORTHO":
        cam.type = "ORTHO"
        cam.ortho_scale = frame.get("ortho_scale", 2.0)
    else:
        cam.type = "PERSP"


def _configure_engine(bpy: Any, scene: Any, shading: str) -> None:
    """Pick render engine + workbench/EEVEE shading for the requested look."""
    render = scene.render
    if shading in WORKBENCH_SHADING:
        render.engine = "BLENDER_WORKBENCH"
        shading_rna = getattr(scene.display, "shading", None)
        if shading_rna is not None:
            if shading == "WIREFRAME":
                shading_rna.type = "WIREFRAME"
            else:
                shading_rna.type = "SOLID"
    else:
        # MATERIAL / RENDERED -> EEVEE. The 5.x engine id is BLENDER_EEVEE_NEXT; fall
        # back to the classic id so we work across versions.
        try:
            render.engine = "BLENDER_EEVEE_NEXT"
        except Exception:  # noqa: BLE001
            render.engine = "BLENDER_EEVEE"


def _render_to_b64(bpy: Any, cam_obj: Any, shading: str, res: int) -> str:
    scene = bpy.context.scene
    render = scene.render
    sh = getattr(getattr(scene, "display", None), "shading", None)
    prev = {
        "camera": scene.camera,
        "engine": getattr(render, "engine", None),
        "x": render.resolution_x,
        "y": render.resolution_y,
        "pct": render.resolution_percentage,
        "filepath": render.filepath,
        "fmt": render.image_settings.file_format,
        # Preserve the user's live viewport workbench look -- SOLID/WIREFRAME mutate type.
        "sh_type": getattr(sh, "type", None),
        "sh_color_type": getattr(sh, "color_type", None),
        "sh_light": getattr(sh, "light", None),
        "sh_shadows": getattr(sh, "show_shadows", None),
        "sh_cavity": getattr(sh, "show_cavity", None),
        "sh_outline": getattr(sh, "show_object_outline", None),
    }
    path = os.path.join(tempfile.gettempdir(), "niua_capture.png")
    try:
        scene.camera = cam_obj
        render.resolution_x = int(res)
        render.resolution_y = int(res)
        render.resolution_percentage = 100
        render.image_settings.file_format = "PNG"
        render.filepath = path
        _configure_engine(bpy, scene, shading)
        # Force the dependency graph to re-evaluate before rendering. The topology overlay
        # mutates materials / material_index and adds a Wireframe modifier via the data API;
        # render.opengl renders the EVALUATED mesh, so without this update both passes render
        # the stale original geometry and come back byte-identical (the bug the judge caught:
        # face-type + wireframe overlays looked like the plain beauty shot).
        try:
            view_layer = getattr(bpy.context, "view_layer", None)
            if view_layer is not None and hasattr(view_layer, "update"):
                view_layer.update()
            dg = getattr(bpy.context, "evaluated_depsgraph_get", None)
            if dg is not None:
                dg()
        except Exception:  # noqa: BLE001 - update is best-effort; render still proceeds
            pass
        # view_context=False renders from the SCENE CAMERA (our positioned capture cam),
        # not the active viewport. Without it, render.opengl ignores the camera framing
        # and every "angle" comes out as the same viewport shot (caught in live GUI).
        bpy.ops.render.opengl(write_still=True, view_context=False)
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")
    finally:
        scene.camera = prev["camera"]
        if prev["engine"] is not None:
            try:
                render.engine = prev["engine"]
            except Exception:  # noqa: BLE001
                pass
        render.resolution_x = prev["x"]
        render.resolution_y = prev["y"]
        render.resolution_percentage = prev["pct"]
        render.filepath = prev["filepath"]
        render.image_settings.file_format = prev["fmt"]
        if sh is not None:
            for attr, key in (
                ("type", "sh_type"),
                ("color_type", "sh_color_type"),
                ("light", "sh_light"),
                ("show_shadows", "sh_shadows"),
                ("show_cavity", "sh_cavity"),
                ("show_object_outline", "sh_outline"),
            ):
                if prev[key] is not None:
                    try:
                        setattr(sh, attr, prev[key])
                    except Exception:  # noqa: BLE001 - restore best-effort only
                        pass


def render(bpy: Any, view: str, shading: str = "SOLID", res: int = 768, obj_name: str | None = None) -> dict[str, Any]:
    """Render one named view (or 'current' = the live scene camera) to base64 PNG.

    Returns an image envelope ``{available, view, mimeType, encoding, data}`` or, on any
    failure (headless / no GPU / no display), ``{available: False, view, reason}``.
    """
    try:
        if view == "current":
            return _render_current(bpy, shading, res)
        center, size = scene_bbox(bpy, obj_name)
        frame = view_camera(center, size, view)
        cam_obj = _ensure_capture_camera(bpy)
        _apply_frame(cam_obj, frame)
        data = _render_to_b64(bpy, cam_obj, shading, res)
        return {"available": True, "view": view, "mimeType": "image/png", "encoding": "base64", "data": data}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "view": view, "reason": str(exc)}


def _render_current(bpy: Any, shading: str, res: int) -> dict[str, Any]:
    """Render the scene's existing camera (or active viewport) without moving anything."""
    scene = bpy.context.scene
    cam_obj = scene.camera
    if cam_obj is None:
        return {"available": False, "view": "current", "reason": "no active scene camera"}
    data = _render_to_b64(bpy, cam_obj, shading, res)
    return {"available": True, "view": "current", "mimeType": "image/png", "encoding": "base64", "data": data}


def capture_views(
    bpy: Any, preset: str = "ortho4", shading: str = "SOLID", res: int = 768, obj_name: str | None = None
) -> dict[str, Any]:
    """Render a preset set of views and return ``{available, images:[...]}``."""
    try:
        center, size = scene_bbox(bpy, obj_name)
        cam_obj = _ensure_capture_camera(bpy)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "images": [], "reason": str(exc)}

    images: list[dict[str, Any]] = []
    if preset == "orbit4":
        frames = [("orbit_%d" % a, orbit_camera(center, size, a)) for a in (0, 90, 180, 270)]
    else:
        names = PRESETS.get(preset, PRESETS["ortho4"])
        frames = [(name, view_camera(center, size, name)) for name in names]

    for name, frame in frames:
        try:
            _apply_frame(cam_obj, frame)
            data = _render_to_b64(bpy, cam_obj, shading, res)
            images.append({"view": name, "mimeType": "image/png", "encoding": "base64", "data": data})
        except Exception as exc:  # noqa: BLE001 - one bad view shouldn't sink the rest
            images.append({"view": name, "available": False, "reason": str(exc)})

    available = any("data" in img for img in images)
    out: dict[str, Any] = {"available": available, "images": images}
    if not available and images:
        out["reason"] = images[0].get("reason", "render failed")
    return out


def turntable(
    bpy: Any, count: int = 6, shading: str = "SOLID", res: int = 768, obj_name: str | None = None
) -> dict[str, Any]:
    """Orbit the object/scene in ``count`` even steps; return ``{available, images:[...]}``."""
    try:
        center, size = scene_bbox(bpy, obj_name)
        cam_obj = _ensure_capture_camera(bpy)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "images": [], "reason": str(exc)}

    count = max(2, min(24, int(count)))
    images: list[dict[str, Any]] = []
    for i in range(count):
        angle = 360.0 * i / count
        frame = orbit_camera(center, size, angle)
        try:
            _apply_frame(cam_obj, frame)
            data = _render_to_b64(bpy, cam_obj, shading, res)
            images.append({"view": "orbit_%d" % round(angle), "mimeType": "image/png", "encoding": "base64", "data": data})
        except Exception as exc:  # noqa: BLE001
            images.append({"view": "orbit_%d" % round(angle), "available": False, "reason": str(exc)})

    available = any("data" in img for img in images)
    out: dict[str, Any] = {"available": available, "images": images}
    if not available and images:
        out["reason"] = images[0].get("reason", "render failed")
    return out
