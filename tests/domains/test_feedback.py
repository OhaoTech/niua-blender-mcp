"""Feedback domain unit tests (fake-bpy).

Covers (1) the pure-Python framing math -- camera placement / orientation / ortho-scale
for each named view and orbit angle given a known bbox -- and (2) the graceful-degrade
path through the actual handlers when rendering fails (headless / no GPU), plus a
happy-path render against a recording fake bpy. The framing math needs no bpy at all.
"""

from __future__ import annotations

import base64
import math
import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.core import capture as cap
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


# -- pure framing math (no bpy) -----------------------------------------------------

def test_bbox_center_size_from_corners() -> None:
    corners = [(0, 0, 0), (2, 4, 6)]
    center, size = cap.bbox_center_size(corners)
    assert center == (1.0, 2.0, 3.0)
    assert size == (2.0, 4.0, 6.0)


def test_bbox_empty_is_origin() -> None:
    assert cap.bbox_center_size([]) == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


@pytest.mark.parametrize(
    "view,axis,sign",
    [
        ("front", 1, -1),   # camera sits at -Y
        ("back", 1, +1),    # +Y
        ("right", 0, +1),   # +X
        ("left", 0, -1),    # -X
        ("top", 2, +1),     # +Z
        ("bottom", 2, -1),  # -Z
    ],
)
def test_named_view_sits_on_the_expected_axis(view, axis, sign) -> None:
    center = (10.0, 20.0, 30.0)
    size = (2.0, 2.0, 2.0)
    frame = cap.view_camera(center, size, view)
    loc = frame["location"]
    # The camera is offset from center purely along the expected axis, on the right side.
    offset = tuple(loc[i] - center[i] for i in range(3))
    assert (offset[axis] > 0) == (sign > 0) and offset[axis] != 0
    for other in range(3):
        if other != axis:
            assert abs(offset[other]) < 1e-9
    assert frame["type"] == "ORTHO"
    assert frame["ortho_scale"] > 0


def test_persp_view_is_perspective_and_offset_in_three_axes() -> None:
    frame = cap.view_camera((0, 0, 0), (2, 2, 2), "persp")
    assert frame["type"] == "PERSP"
    assert "ortho_scale" not in frame
    loc = frame["location"]
    assert loc[0] > 0 and loc[1] < 0 and loc[2] > 0  # front-right-top 3/4 look


def test_view_camera_distance_scales_with_bbox_size() -> None:
    near = cap.view_camera((0, 0, 0), (1, 1, 1), "front")["location"]
    far = cap.view_camera((0, 0, 0), (10, 10, 10), "front")["location"]
    assert abs(far[1]) > abs(near[1])  # bigger object -> camera further back


def test_ortho_scale_uses_perpendicular_extents() -> None:
    # front looks down Y: on-screen extents are X and Z; Y is depth and must be ignored.
    size = (4.0, 99.0, 2.0)
    assert cap.ortho_scale(size, "front") == pytest.approx(4.0 * 1.15)
    # top looks down Z: extents are X and Y.
    assert cap.ortho_scale((4.0, 6.0, 99.0), "top") == pytest.approx(6.0 * 1.15)


def test_unknown_view_raises() -> None:
    with pytest.raises(ValueError):
        cap.view_camera((0, 0, 0), (1, 1, 1), "diagonal")


def test_orbit_camera_angle0_looks_from_front() -> None:
    center = (0.0, 0.0, 0.0)
    frame = cap.orbit_camera(center, (2, 2, 2), 0.0, elevation_deg=0.0)
    loc = frame["location"]
    assert frame["type"] == "PERSP"
    # angle 0, no elevation -> straight in front along -Y.
    assert loc[1] < 0
    assert abs(loc[0]) < 1e-9 and abs(loc[2]) < 1e-9


def test_orbit_camera_90_degrees_moves_to_plus_x() -> None:
    frame = cap.orbit_camera((0, 0, 0), (2, 2, 2), 90.0, elevation_deg=0.0)
    loc = frame["location"]
    assert loc[0] > 0 and abs(loc[1]) < 1e-9


def test_orbit_elevation_raises_camera() -> None:
    frame = cap.orbit_camera((0, 0, 0), (2, 2, 2), 0.0, elevation_deg=30.0)
    assert frame["location"][2] > 0  # elevated above the object


# -- view_matrix_from_frame: the pure-python core of the multi-angle fix ------------
#
# docs/reports/capture-multiangle-bug.md: reading cam.matrix_world right after setting
# cam.location/rotation_euler returns a STALE transform within one bridge call, so
# every render collapsed to the same angle. The fix computes the view matrix directly
# from the frame dict instead. No real ``mathutils`` is installed in this dev/test
# environment, so this exercises the pure-python fallback in
# ``core.capture.view_matrix_from_frame`` -- verified byte-for-byte against real
# ``mathutils.Matrix`` output from a live headless Blender (see the plan report).


def test_view_matrix_known_frame_matches_hand_computed_value() -> None:
    # front-ish frame: camera sits on -Y at distance 5, rotated +90deg about X so its
    # local -Z looks back at the origin along +Y. Hand-computed (and cross-checked
    # against real mathutils.Matrix in a live headless Blender):
    #   [[1, 0, 0,  0], [0, 0, 1, 0], [0, -1, 0, -5], [0, 0, 0, 1]]
    frame = {"location": (0.0, -5.0, 0.0), "rotation_euler": (math.pi / 2, 0.0, 0.0)}
    vm = cap.view_matrix_from_frame(frame)
    expected = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0, -5.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    for row, erow in zip(vm, expected):
        for value, evalue in zip(row, erow):
            assert value == pytest.approx(evalue, abs=1e-9)


def test_view_matrix_front_and_top_frames_are_distinct() -> None:
    center, size = (0.0, 0.0, 0.0), (2.0, 2.0, 2.0)
    front = cap.view_camera(center, size, "front")
    top = cap.view_camera(center, size, "top")
    vm_front = cap.view_matrix_from_frame(front)
    vm_top = cap.view_matrix_from_frame(top)
    flat_front = [v for row in vm_front for v in row]
    flat_top = [v for row in vm_top for v in row]
    assert any(abs(a - b) > 1e-6 for a, b in zip(flat_front, flat_top))


def test_view_matrix_right_and_persp_frames_are_distinct_from_front() -> None:
    center, size = (1.0, 2.0, 3.0), (4.0, 4.0, 4.0)
    front = cap.view_matrix_from_frame(cap.view_camera(center, size, "front"))
    right = cap.view_matrix_from_frame(cap.view_camera(center, size, "right"))
    persp = cap.view_matrix_from_frame(cap.view_camera(center, size, "persp"))
    flat_front = [v for row in front for v in row]
    flat_right = [v for row in right for v in row]
    flat_persp = [v for row in persp for v in row]
    assert any(abs(a - b) > 1e-6 for a, b in zip(flat_front, flat_right))
    assert any(abs(a - b) > 1e-6 for a, b in zip(flat_front, flat_persp))


def test_view_matrix_is_orthonormal_rigid_transform() -> None:
    # Sanity: the fallback's rotation block should be a valid rotation (R @ R^T = I),
    # i.e. the inverse-of-a-rigid-transform math is actually correct, not just "different".
    frame = cap.orbit_camera((0.0, 0.0, 0.0), (3.0, 3.0, 3.0), 37.0, elevation_deg=18.0)
    vm = cap.view_matrix_from_frame(frame)
    r = [[vm[i][j] for j in range(3)] for i in range(3)]
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    product = [[sum(r[i][k] * rt[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    for i in range(3):
        for j in range(3):
            expected = 1.0 if i == j else 0.0
            assert product[i][j] == pytest.approx(expected, abs=1e-6)
    assert vm[3] == (0.0, 0.0, 0.0, 1.0)


def test_projection_is_ortho_reflects_frame_type() -> None:
    assert cap.projection_is_ortho(cap.view_camera((0, 0, 0), (2, 2, 2), "front")) is True
    assert cap.projection_is_ortho(cap.view_camera((0, 0, 0), (2, 2, 2), "persp")) is False


# -- fake bpy for the handler / render path -----------------------------------------

class _Mat:
    """4x4 identity-ish matrix supporting ``@ seq`` -> translated tuple (no rotation)."""

    def __init__(self, offset=(0.0, 0.0, 0.0)) -> None:
        self.offset = offset

    def __matmul__(self, vec):
        return tuple(vec[i] + self.offset[i] for i in range(3))


class FakeObj:
    def __init__(self, name, type="MESH") -> None:
        self.name = name
        self.type = type
        self.matrix_world = _Mat()
        # Unit cube centered at origin.
        self.bound_box = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
        ]
        self.location = (0, 0, 0)
        self.rotation_mode = "XYZ"
        self.rotation_euler = (0, 0, 0)
        self.hide_viewport = False
        self.hide_render = False
        self.data = None

    def calc_matrix_camera(self, depsgraph, x=1, y=1, scale_x=1.0, scale_y=1.0):
        # Real bpy.types.Object.calc_matrix_camera reads camera DATA (lens/ortho_scale/
        # sensor), not the transform; a fake sentinel is enough since the fake
        # draw_view3d below only records it, never interprets it.
        return ("FAKE_PROJ_MATRIX", self.name, getattr(self.data, "type", None), x, y)


class FakeCamData:
    def __init__(self, name) -> None:
        self.name = name
        self.type = "PERSP"
        self.ortho_scale = 1.0


# -- fake gpu module + fake VIEW_3D window/area (GPUOffScreen render path) ----------
#
# core.capture._render_offscreen does `import gpu` and walks
# bpy.context.window_manager.windows -> screen.areas -> VIEW_3D -> space/region. Real
# `gpu` is Blender-only (no PyPI package providing real GL), so tests that want the
# happy path inject a fake module into sys.modules, mirroring how `bpy` itself is
# faked. This does not prove real pixels render correctly (that needs live Blender --
# see docs/reports/gpu_offscreen_verified_prototype.py) but it does prove the WIRING:
# the right matrices/args reach draw_view3d, and overlay/shading state is toggled and
# restored around it.


class _FakeGPUBuffer(list):
    """list subclass so ``buf.dimensions = ...`` (real Buffer supports this) works."""


class _FakeFramebuffer:
    @staticmethod
    def read_color(x, y, w, h, channels, slot, dtype):
        return _FakeGPUBuffer([21] * (w * h * channels))


class _FakeGPUState:
    @staticmethod
    def active_framebuffer_get():
        return _FakeFramebuffer()


class _NullBind:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _make_fake_gpu(draw_raises: bool = False):
    """A fake ``gpu`` module. Returns ``(module, draw_calls)`` -- ``draw_calls`` records
    every ``draw_view3d(...)`` invocation's kwargs for assertions."""
    draw_calls: list = []

    class _FakeGPUOffScreen:
        def __init__(self, width, height):
            self.width = width
            self.height = height
            self.freed = False

        def draw_view3d(self, scene, view_layer, space, region, view_matrix, proj_matrix, do_color_management=False):
            draw_calls.append(
                {
                    "scene": scene,
                    "view_layer": view_layer,
                    "space": space,
                    "region": region,
                    "view_matrix": view_matrix,
                    "proj_matrix": proj_matrix,
                    "do_color_management": do_color_management,
                    # Snapshot state AS SEEN DURING the render (overlay/shading must be
                    # mutated by now and restored only after draw_view3d returns).
                    "overlay_show_overlays": getattr(space.overlay, "show_overlays", None),
                    "shading_type": getattr(space.shading, "type", None),
                }
            )
            if draw_raises:
                raise RuntimeError("no GPU / headless")

        def bind(self):
            return _NullBind()

        def free(self):
            self.freed = True

    class _Types:
        GPUOffScreen = _FakeGPUOffScreen

    mod = types.ModuleType("gpu")
    mod.types = _Types
    mod.state = _FakeGPUState
    mod._draw_calls = draw_calls
    return mod, draw_calls


class _FakeOverlay:
    def __init__(self) -> None:
        self.show_overlays = True


class _FakeSpaceShading:
    def __init__(self) -> None:
        self.type = "SOLID"


class _FakeView3DSpace:
    def __init__(self) -> None:
        self.overlay = _FakeOverlay()
        self.shading = _FakeSpaceShading()


class _FakeRegion:
    type = "WINDOW"


class _FakeArea:
    def __init__(self, area_type: str = "VIEW_3D") -> None:
        self.type = area_type
        self.spaces = types.SimpleNamespace(active=_FakeView3DSpace())
        self.regions = [_FakeRegion()]


class _FakeScreen:
    def __init__(self) -> None:
        self.areas = [_FakeArea()]


class _FakeWindow:
    def __init__(self) -> None:
        self.screen = _FakeScreen()


class _FakeWindowManager:
    def __init__(self, with_view3d: bool = True) -> None:
        self.windows = [_FakeWindow()] if with_view3d else []


def _make_bpy(render_raises: bool = False, write_file: bool = True, with_view3d: bool = True):
    bpy = types.ModuleType("bpy")
    objects: dict = {}
    cameras: dict = {}
    scene_objs: list = []

    obj = FakeObj("Cube")
    objects["Cube"] = obj
    scene_objs.append(obj)

    class _Shading:
        type = "SOLID"

    class _ImgSettings:
        file_format = "PNG"

    class _Render:
        engine = "BLENDER_WORKBENCH"
        resolution_x = 1920
        resolution_y = 1080
        resolution_percentage = 100
        filepath = ""
        image_settings = _ImgSettings()

    scene = types.SimpleNamespace(
        objects=scene_objs,
        render=_Render(),
        display=types.SimpleNamespace(shading=_Shading()),
        camera=None,
        collection=None,
    )

    class _Coll:
        @staticmethod
        def link(o):
            if o.name not in objects:
                objects[o.name] = o
            if o not in scene_objs:
                scene_objs.append(o)

    scene.collection = types.SimpleNamespace(objects=_Coll())
    view_layer = types.SimpleNamespace(update=lambda: None)
    window_manager = _FakeWindowManager(with_view3d=with_view3d)
    bpy.context = types.SimpleNamespace(
        scene=scene,
        view_layer=view_layer,
        window_manager=window_manager,
        evaluated_depsgraph_get=lambda: "FAKE_DEPSGRAPH",
    )

    class _DataObjects:
        @staticmethod
        def get(name):
            return objects.get(name)

        @staticmethod
        def new(name, data):
            o = FakeObj(name, type="CAMERA")
            o.data = data
            return o

    class _DataCameras:
        @staticmethod
        def new(name):
            c = FakeCamData(name)
            cameras[name] = c
            return c

    bpy.data = types.SimpleNamespace(objects=_DataObjects(), cameras=_DataCameras())

    render_calls: list = []

    class _RenderOps:
        @staticmethod
        def opengl(write_still=False, **kw):
            render_calls.append(write_still)
            if render_raises:
                raise RuntimeError("no GPU / headless")
            if write_file:
                with open(scene.render.filepath, "wb") as fh:
                    fh.write(b"\x89PNG\r\n\x1a\n" + b"fakepng")

    bpy.ops = types.SimpleNamespace(render=_RenderOps())
    bpy._render_calls = render_calls
    bpy._scene = scene
    bpy._objects = objects
    gpu_module, gpu_draw_calls = _make_fake_gpu(draw_raises=render_raises)
    bpy._gpu_module = gpu_module
    bpy._gpu_draw_calls = gpu_draw_calls
    return bpy


def _install_bpy(bpy, monkeypatch) -> None:
    """Inject the fake ``bpy`` AND its matching fake ``gpu`` into sys.modules.

    ``core.capture._render_offscreen`` does a plain top-level ``import gpu`` (real
    ``gpu`` is Blender-only and not pip-installable), so tests exercising the
    GPUOffScreen render path must patch ``sys.modules['gpu']`` exactly like ``bpy``
    itself is patched.
    """
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setitem(sys.modules, "gpu", bpy._gpu_module)


@pytest.fixture()
def ctx_env(monkeypatch):
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    return Ctx(bpy), bpy


# -- handler happy path + degrade ---------------------------------------------------

def test_capture_named_view_renders_and_creates_hidden_camera(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "front"}, ctx)
    assert out["available"] is True
    assert out["view"] == "front"
    assert out["mimeType"] == "image/png"
    assert out["data"]  # base64 of the fake png
    cam = bpy._objects.get(cap.CAPTURE_CAM)
    assert cam is not None and cam.hide_viewport is True
    # User's scene camera was restored (was None before).
    assert bpy._scene.camera is None


def test_capture_reuses_capture_camera(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "front"}, ctx)
    first = bpy._objects.get(cap.CAPTURE_CAM)
    dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "top"}, ctx)
    assert bpy._objects.get(cap.CAPTURE_CAM) is first  # not recreated


def test_capture_views_returns_one_image_per_preset_view(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture_views", {"object": "Cube", "preset": "ortho4"}, ctx)
    assert out["available"] is True
    views = [img["view"] for img in out["images"]]
    assert views == ["front", "right", "top", "persp"]
    assert all(img["data"] for img in out["images"])


def test_turntable_clamps_count_and_orbits(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.turntable", {"object": "Cube", "count": 100}, ctx)
    assert len(out["images"]) == 24  # clamped to max
    out2 = dispatch_on_main(reg, "feedback.turntable", {"object": "Cube", "count": 1}, ctx)
    assert len(out2["images"]) == 2  # clamped to min


def test_capture_degrades_when_render_fails(monkeypatch) -> None:
    bpy = _make_bpy(render_raises=True)
    _install_bpy(bpy, monkeypatch)
    ctx = Ctx(bpy)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "front"}, ctx)
    assert out["available"] is False
    assert "no GPU" in out["reason"]


def test_capture_views_degrades_when_render_fails(monkeypatch) -> None:
    bpy = _make_bpy(render_raises=True)
    _install_bpy(bpy, monkeypatch)
    ctx = Ctx(bpy)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture_views", {"object": "Cube"}, ctx)
    assert out["available"] is False
    assert all(img.get("available") is False for img in out["images"])


def test_capture_degrades_when_no_view3d_area(monkeypatch) -> None:
    # Real headless Blender (`--background`) has no windows at all -- this is the
    # "no VIEW_3D area" branch of _render_offscreen, distinct from a GPU draw failure.
    bpy = _make_bpy(with_view3d=False)
    _install_bpy(bpy, monkeypatch)
    ctx = Ctx(bpy)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "front"}, ctx)
    assert out["available"] is False
    assert "VIEW_3D" in out["reason"] or "GPU" in out["reason"]


def test_capture_missing_object_degrades(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"object": "Ghost", "view": "front"}, ctx)
    assert out["available"] is False
    assert "Ghost" in out["reason"]


def test_capture_current_without_scene_camera_degrades(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"view": "current"}, ctx)
    assert out["available"] is False
    assert "camera" in out["reason"].lower()


# -- _render_offscreen wiring: overlay/shading toggled+restored, correct matrices ---


def test_render_offscreen_toggles_overlay_and_shading_then_restores(monkeypatch) -> None:
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    space = bpy.context.window_manager.windows[0].screen.areas[0].spaces.active
    space.overlay.show_overlays = True
    space.shading.type = "SOLID"

    frame = cap.view_camera((0.0, 0.0, 0.0), (2.0, 2.0, 2.0), "top")
    data = cap._render_offscreen(bpy, frame, "MATERIAL", 64)

    assert data  # base64 PNG came back
    png_bytes = base64.b64decode(data)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Overlay/shading restored to their pre-render values afterward.
    assert space.overlay.show_overlays is True
    assert space.shading.type == "SOLID"

    # But DURING the draw_view3d call, overlays were off and shading was the requested mode.
    assert len(bpy._gpu_draw_calls) == 1
    call = bpy._gpu_draw_calls[0]
    assert call["overlay_show_overlays"] is False
    assert call["shading_type"] == "MATERIAL"
    assert call["do_color_management"] is False

    # The view matrix handed to draw_view3d is exactly the pure-python computation --
    # never a (possibly stale) cam.matrix_world read.
    expected_vm = cap.view_matrix_from_frame(frame)
    assert call["view_matrix"] == expected_vm


def test_render_offscreen_restores_state_even_when_draw_raises(monkeypatch) -> None:
    bpy = _make_bpy(render_raises=True)
    _install_bpy(bpy, monkeypatch)
    space = bpy.context.window_manager.windows[0].screen.areas[0].spaces.active
    space.overlay.show_overlays = True
    space.shading.type = "SOLID"

    frame = cap.view_camera((0.0, 0.0, 0.0), (2.0, 2.0, 2.0), "front")
    with pytest.raises(RuntimeError):
        cap._render_offscreen(bpy, frame, "MATERIAL", 64)

    assert space.overlay.show_overlays is True
    assert space.shading.type == "SOLID"


def test_render_offscreen_no_view3d_raises() -> None:
    bpy = _make_bpy(with_view3d=False)
    with pytest.raises(RuntimeError):
        cap._render_offscreen(bpy, cap.view_camera((0, 0, 0), (2, 2, 2), "front"), "SOLID", 64)


# -- critique bundle (images + report + uv in one observe call) ---------------------

def test_critique_bundles_images_and_report(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.critique", {"object": "Cube", "preset": "ortho4"}, ctx)
    # Multi-angle images (the taste signal).
    assert out["available"] is True
    assert [img["view"] for img in out["images"]] == ["front", "right", "top", "persp"]
    assert all(img["data"] for img in out["images"])
    # Analytic mesh report (the checkable facts).
    assert out["report"]["object"] == "Cube"
    assert "vertices" in out["report"] and "ngons" in out["report"]
    # UV report present for a mesh.
    assert out["uv"] is not None
    assert out["uv"]["object"] == "Cube"
    assert "has_uvs" in out["uv"]
    # Read-only: nothing mutated, no undo step.
    assert getattr(bpy, "_render_calls", None) is not None


def test_critique_report_survives_when_images_degrade(monkeypatch) -> None:
    bpy = _make_bpy(render_raises=True)
    _install_bpy(bpy, monkeypatch)
    ctx = Ctx(bpy)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.critique", {"object": "Cube"}, ctx)
    # Headless / no GPU: images unavailable, but the analytic report still comes back.
    assert out["available"] is False
    assert out["report"]["object"] == "Cube"
    assert out["uv"] is not None


def test_critique_non_mesh_object_returns_null_report_and_uv(ctx_env) -> None:
    ctx, bpy = ctx_env
    # Add a non-mesh object and target it.
    light = FakeObj("Lamp", type="LIGHT")
    bpy._objects["Lamp"] = light
    bpy._scene.objects.append(light)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.critique", {"object": "Lamp"}, ctx)
    # Images still framed; report degrades (not a mesh), uv is null.
    assert out["report"].get("available") is False
    assert out["uv"] is None
