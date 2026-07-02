"""The rendering engine behind the feedback subsystem -- the agent's eyes.

The anti-blob principle from the project's origin: to judge *form* you must see it from
several angles, not one lucky shot. This module owns a dedicated, hidden capture camera
so the user's viewport and view never move, computes faithful framing for named views
(front/back/left/right/top/bottom/persp) around an object's (or the whole scene's) world
bounding box, and renders it deterministically.

Two layers:

* **Pure-Python framing + view-matrix math** (``bbox_*`` / ``view_camera`` /
  ``orbit_camera`` / ``view_matrix_from_frame``) takes a bbox center + size and returns
  a camera ``location``, ``rotation_euler`` and (for orthographic views) an
  ``ortho_scale`` -- and can turn that frame into a world->view matrix without ever
  reading ``cam.matrix_world`` (see ``_render_offscreen`` below for why). No ``bpy``
  involved, so it is unit-testable against a fake bpy / plain numbers.
* **bpy-bound rendering** (``render`` / ``capture_views`` / ``turntable``) which creates
  or reuses the hidden camera, then renders each frame via ``_render_offscreen`` --
  ``gpu.types.GPUOffScreen.draw_view3d`` fed the pure-Python view matrix -- to a base64
  PNG. Every failure (headless, no GPU, no VIEW_3D area) degrades to
  ``{"available": False, "reason": ...}`` exactly like the original ``feedback.capture``.
  (``_render_to_b64``, the older ``bpy.ops.render.opengl``-based renderer, is kept only
  for ``view="current"``, which renders the user's own already-positioned scene camera
  and so never hits the stale-matrix bug -- see its docstring.)

``bpy`` is imported lazily inside the bpy-bound functions, never at module top, so the
framing math stays importable under fake-bpy unit tests.
"""

from __future__ import annotations

import base64
import math
import os
import struct
import tempfile
import zlib
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
# Pure-Python view-matrix math (unit-testable, no bpy) -- the core of the multi-angle fix
# --------------------------------------------------------------------------------------
#
# ROOT CAUSE (docs/reports/capture-multiangle-bug.md): setting ``cam.location`` /
# ``cam.rotation_euler`` does NOT synchronously update ``cam.matrix_world`` -- the
# recompute is deferred to a depsgraph pass that never lands inside a single bridge
# call. Every render path that read ``cam.matrix_world`` right after positioning the
# camera therefore rendered a STALE transform, collapsing distinct angles (front/top/
# right) into the same image. The fix: never read ``cam.matrix_world`` for the render
# transform -- compute the view matrix directly, in pure Python, from the frame dict
# that ``view_camera``/``orbit_camera`` already produced.


def _matmul4(a: tuple, b: tuple) -> tuple:
    """4x4 matrix multiply on plain nested tuples (the no-mathutils fallback path)."""
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4))
        for i in range(4)
    )


def _euler_xyz_to_matrix4(rot: tuple[float, float, float]) -> tuple:
    """Rotation matrix for Blender's 'XYZ' Euler order: R = Rz(z) @ Ry(y) @ Rx(x).

    Verified against ``mathutils.Euler(rot, 'XYZ').to_matrix()`` for arbitrary angles
    (see the plan's Task 1 investigation) -- Blender's intrinsic X-then-Y-then-Z order
    is the extrinsic Z-Y-X composition applied to a column vector.
    """
    x, y, z = rot
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    rx = ((1.0, 0.0, 0.0, 0.0), (0.0, cx, -sx, 0.0), (0.0, sx, cx, 0.0), (0.0, 0.0, 0.0, 1.0))
    ry = ((cy, 0.0, sy, 0.0), (0.0, 1.0, 0.0, 0.0), (-sy, 0.0, cy, 0.0), (0.0, 0.0, 0.0, 1.0))
    rz = ((cz, -sz, 0.0, 0.0), (sz, cz, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    return _matmul4(_matmul4(rz, ry), rx)


def _translation_matrix4(loc: tuple[float, float, float]) -> tuple:
    x, y, z = loc
    return ((1.0, 0.0, 0.0, x), (0.0, 1.0, 0.0, y), (0.0, 0.0, 1.0, z), (0.0, 0.0, 0.0, 1.0))


def _invert_affine4(m: tuple) -> tuple:
    """Invert a rigid transform (rotation + translation, no scale/shear): for
    ``M = [R t; 0 1]``, ``inverse = [R^T  -R^T@t; 0 1]``.
    """
    r = tuple(tuple(m[i][j] for j in range(3)) for i in range(3))
    rt = tuple(tuple(r[j][i] for j in range(3)) for i in range(3))
    t = (m[0][3], m[1][3], m[2][3])
    neg_rt_t = tuple(-sum(rt[i][k] * t[k] for k in range(3)) for i in range(3))
    return (
        (rt[0][0], rt[0][1], rt[0][2], neg_rt_t[0]),
        (rt[1][0], rt[1][1], rt[1][2], neg_rt_t[1]),
        (rt[2][0], rt[2][1], rt[2][2], neg_rt_t[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def view_matrix_from_frame(frame: dict[str, Any]) -> Any:
    """The capture camera's WORLD->VIEW matrix, computed PURE-PYTHON from a frame dict.

    ``frame`` is exactly what ``view_camera``/``orbit_camera`` return: ``location`` +
    ``rotation_euler`` (radians, 'XYZ' order). NEVER reads ``cam.matrix_world`` -- see
    the module-level note above. Uses real ``mathutils`` when available (inside
    Blender, returns a ``mathutils.Matrix``); falls back to an equivalent hand-rolled
    4x4 (nested tuples) so this stays unit-testable under fake-bpy with no real
    ``mathutils`` installed.
    """
    loc = frame["location"]
    rot = frame["rotation_euler"]
    try:
        import mathutils  # noqa: PLC0415 - real Blender only

        cam_world = mathutils.Matrix.Translation(mathutils.Vector(loc)) @ mathutils.Euler(rot, "XYZ").to_matrix().to_4x4()
        return cam_world.inverted()
    except Exception:  # noqa: BLE001 - fake-bpy unit tests: pure-python fallback
        cam_world = _matmul4(_translation_matrix4(loc), _euler_xyz_to_matrix4(rot))
        return _invert_affine4(cam_world)


def projection_is_ortho(frame: dict[str, Any]) -> bool:
    """Whether a frame calls for an orthographic projection (vs. perspective)."""
    return frame.get("type") == "ORTHO"


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
    """Render ``cam_obj`` as-is via ``bpy.ops.render.opengl`` (the pre-fix path).

    Kept ONLY for ``_render_current`` (``view="current"``): that path renders the
    user's own scene camera exactly as it already sits, without this call setting its
    transform first, so it never hits the stale-``matrix_world`` bug that motivated
    ``_render_offscreen`` below (docs/reports/capture-multiangle-bug.md). Every other
    caller that positions the hidden capture camera from a frame -- ``render``/
    ``capture_views``/``turntable`` and the topology/silhouette eyes -- uses
    ``_render_offscreen`` instead.
    """
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


# --------------------------------------------------------------------------------------
# GPUOffScreen rendering (THE fix): deterministic, view-context-independent.
# --------------------------------------------------------------------------------------
#
# Ports docs/reports/gpu_offscreen_verified_prototype.py, the canonical live-verified
# reference (proven: a cone's front renders a triangle, top a circle, 4/4 distinct
# angles). Renders via gpu.types.GPUOffScreen.draw_view3d fed an explicit view + proj
# matrix, so it is independent of scene.camera / viewport state / depsgraph timing --
# the class of bug that sank every render.opengl-based attempt.


def _find_view3d_space_region(bpy: Any) -> tuple[Any, Any]:
    """Locate a live VIEW_3D space + WINDOW region across all open windows.

    ``GPUOffScreen.draw_view3d`` needs a real viewport space/region to borrow shading
    settings and GL state from. Headless Blender (``--background``, no GUI) has no
    windows at all, so this returns ``(None, None)`` and the caller degrades
    gracefully -- exactly the prototype's search pattern.
    """
    wm = getattr(bpy.context, "window_manager", None)
    for win in getattr(wm, "windows", []) if wm is not None else []:
        screen = getattr(win, "screen", None)
        for area in getattr(screen, "areas", []) if screen is not None else []:
            if getattr(area, "type", None) == "VIEW_3D":
                space = area.spaces.active
                region = next(
                    (r for r in getattr(area, "regions", []) if getattr(r, "type", None) == "WINDOW"),
                    None,
                )
                if space is not None and region is not None:
                    return space, region
    return None, None


def _png_bytes(width: int, height: int, flat_ubyte: Any) -> bytes:
    """Pure-Python RGBA8 PNG encoder -- ports the verified prototype's encoder verbatim.

    GPU framebuffers are read bottom-up; PNG rows are top-down, so rows are emitted in
    reverse to flip the image right-side-up.
    """
    stride = width * 4
    rows = [b"\x00" + bytes(flat_ubyte[y * stride:(y + 1) * stride]) for y in range(height - 1, -1, -1)]
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _read_offscreen_png(offscreen: Any, res: int) -> str:
    """Bind the offscreen, read RGBA8 pixels, PNG-encode, return base64."""
    import gpu  # noqa: PLC0415 - real Blender only

    with offscreen.bind():
        buf = gpu.state.active_framebuffer_get().read_color(0, 0, res, res, 4, 0, "UBYTE")
    buf.dimensions = res * res * 4
    return base64.b64encode(_png_bytes(res, res, list(buf))).decode("ascii")


def _render_offscreen(bpy: Any, frame: dict[str, Any], shading: str, res: int) -> str:
    """Render one ``frame`` via ``GPUOffScreen.draw_view3d`` fed a pure-Python view matrix.

    THE render path for every eye that positions the hidden capture camera from a
    frame: ``render``/``capture_views``/``turntable`` (this module) and the topology/
    silhouette eyes. It NEVER reads ``cam.matrix_world`` -- the view matrix comes from
    ``view_matrix_from_frame(frame)`` -- because setting the camera's transform and
    reading ``matrix_world`` back in the same bridge call returns a stale value
    (docs/reports/capture-multiangle-bug.md). The projection matrix instead comes from
    ``cam.calc_matrix_camera``, which reads camera DATA (lens/ortho_scale/sensor) that
    Blender updates immediately -- only object TRANSFORMS are deferred.

    Disables viewport overlays and sets ``space.shading.type`` for the duration of the
    render (both restored in ``finally``) so the 3D cursor / gizmos / user's own
    viewport look never leak into a capture and are never left mutated afterward.

    Raises on any failure (headless, no GPU, no VIEW_3D area, ...); callers already
    wrap frame renders in try/except and degrade to ``{"available": False, "reason":
    ...}`` -- this function does not swallow exceptions itself, only restores state.
    """
    res = int(res)
    space, region = _find_view3d_space_region(bpy)
    if space is None or region is None:
        raise RuntimeError("no VIEW_3D area with a GPU context available for offscreen capture (headless / no GUI)")

    import gpu  # noqa: PLC0415 - real Blender only; absence -> graceful degrade upstream

    scene = bpy.context.scene
    view_layer = getattr(bpy.context, "view_layer", None)
    cam_obj = _ensure_capture_camera(bpy)
    cam_data = cam_obj.data

    overlay_rna = getattr(space, "overlay", None)
    shading_rna = getattr(space, "shading", None)
    prev_overlay = getattr(overlay_rna, "show_overlays", None)
    prev_shading_type = getattr(shading_rna, "type", None)
    prev_engine = getattr(scene.render, "engine", None)

    offscreen = None
    try:
        _apply_frame(cam_obj, frame)
        cam_obj.hide_viewport = True

        _configure_engine(bpy, scene, shading)
        if overlay_rna is not None:
            overlay_rna.show_overlays = False
        if shading_rna is not None:
            shading_rna.type = shading

        # Force the dependency graph to re-evaluate before rendering. The topology/
        # silhouette eyes mutate materials / material_index and add a Wireframe
        # modifier via the data API; draw_view3d renders the EVALUATED mesh, so without
        # this update a pass can render stale geometry (mirrors the same fix that was
        # needed for the old render.opengl path).
        try:
            if view_layer is not None and hasattr(view_layer, "update"):
                view_layer.update()
        except Exception:  # noqa: BLE001 - update is best-effort; render still proceeds
            pass

        view_matrix = view_matrix_from_frame(frame)
        dg = bpy.context.evaluated_depsgraph_get()
        proj_matrix = cam_obj.calc_matrix_camera(dg, x=res, y=res)

        offscreen = gpu.types.GPUOffScreen(res, res)
        offscreen.draw_view3d(
            scene, view_layer, space, region, view_matrix, proj_matrix, do_color_management=False,
        )
        return _read_offscreen_png(offscreen, res)
    finally:
        if offscreen is not None:
            offscreen.free()
        if overlay_rna is not None and prev_overlay is not None:
            overlay_rna.show_overlays = prev_overlay
        if shading_rna is not None and prev_shading_type is not None:
            shading_rna.type = prev_shading_type
        if prev_engine is not None:
            try:
                scene.render.engine = prev_engine
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
        data = _render_offscreen(bpy, frame, shading, res)
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
        _ensure_capture_camera(bpy)
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
            data = _render_offscreen(bpy, frame, shading, res)
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
        _ensure_capture_camera(bpy)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "images": [], "reason": str(exc)}

    count = max(2, min(24, int(count)))
    images: list[dict[str, Any]] = []
    for i in range(count):
        angle = 360.0 * i / count
        frame = orbit_camera(center, size, angle)
        try:
            data = _render_offscreen(bpy, frame, shading, res)
            images.append({"view": "orbit_%d" % round(angle), "mimeType": "image/png", "encoding": "base64", "data": data})
        except Exception as exc:  # noqa: BLE001
            images.append({"view": "orbit_%d" % round(angle), "available": False, "reason": str(exc)})

    available = any("data" in img for img in images)
    out: dict[str, Any] = {"available": available, "images": images}
    if not available and images:
        out["reason"] = images[0].get("reason", "render failed")
    return out
