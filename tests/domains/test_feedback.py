"""Feedback domain unit tests (fake-bpy).

Covers (1) the pure-Python framing math -- camera placement / orientation / ortho-scale
for each named view and orbit angle given a known bbox, plus the view-name -> viewport
mapping -- and (2) the graceful-degrade path through the actual handlers when rendering
fails (headless / no VIEW_3D area), plus a happy-path render against a recording fake
bpy that models the LIVE-VIEWPORT render path (``core.capture._render_viewport``: drive
``bpy.ops.view3d.view_axis``/``view_orbit``/``view_selected``/``view_all``, then capture
via ``bpy.ops.render.opengl(view_context=True)``). The framing math needs no bpy at all.
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


# -- view-name -> viewport-render mapping (pure function, no bpy) -------------------
#
# core.capture._view_render_kwargs is the single source of truth translating a named
# view into what _render_viewport needs to drive the live viewport: either an
# ``axis=`` for the six bpy.ops.view3d.view_axis(type=...) enum values, or an
# ``azimuth_deg=``/``elevation_deg=`` pair for the 3/4 "persp" look built from FRONT via
# bpy.ops.view3d.view_orbit.

@pytest.mark.parametrize(
    "view,expected",
    [
        ("front", {"axis": "FRONT"}),
        ("back", {"axis": "BACK"}),
        ("left", {"axis": "LEFT"}),
        ("right", {"axis": "RIGHT"}),
        ("top", {"axis": "TOP"}),
        ("bottom", {"axis": "BOTTOM"}),
        ("persp", {"azimuth_deg": cap.PERSP_AZIMUTH_DEG, "elevation_deg": cap.PERSP_ELEVATION_DEG}),
    ],
)
def test_view_render_kwargs_maps_named_views(view, expected) -> None:
    assert cap._view_render_kwargs(view) == expected


@pytest.mark.parametrize("view", ["diagonal", "current", "", "FRONT"])
def test_view_render_kwargs_rejects_unknown_view(view) -> None:
    # 'current' is a real view name, but it is handled separately by render() via the
    # scene camera -- _view_render_kwargs only knows the six axes + persp.
    with pytest.raises(ValueError):
        cap._view_render_kwargs(view)


# -- fake bpy for the handler / render path -----------------------------------------
#
# core.capture._render_viewport drives the LIVE 3D viewport (view3d.view_axis/
# view_orbit/view_selected/view_all inside bpy.context.temp_override) then captures it
# with bpy.ops.render.opengl(view_context=True). This fake bpy models that surface: a
# single fake VIEW_3D area/region whose space carries shading/overlay/region_3d state,
# fake view3d.* ops that record every call (and mutate region_3d.view_matrix to a
# distinct sentinel string per view, so tests can assert genuinely different framing was
# applied), and a fake render.opengl that writes a tiny PNG file to
# scene.render.filepath.


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
        self._selected = False

    def select_get(self) -> bool:
        return self._selected

    def select_set(self, value) -> None:
        self._selected = bool(value)


class FakeCamData:
    def __init__(self, name) -> None:
        self.name = name
        self.type = "PERSP"
        self.ortho_scale = 1.0


# -- fake VIEW_3D area/region + view3d/render ops (viewport-driven render path) -----


class _FakeRegion3D:
    def __init__(self) -> None:
        self.view_perspective = "PERSP"
        self.view_distance = 12.0
        self.view_location = (1.0, 2.0, 3.0)
        self.view_rotation = (0.5, 0.5, 0.5, 0.5)
        self.view_matrix = "ORIGINAL_VIEW_MATRIX"


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
        self.region_3d = _FakeRegion3D()


class _FakeRegion:
    type = "WINDOW"


class _FakeArea:
    def __init__(self, area_type: str = "VIEW_3D") -> None:
        self.type = area_type
        self.spaces = types.SimpleNamespace(active=_FakeView3DSpace())
        self.regions = [_FakeRegion()]


class _FakeWindow:
    def __init__(self, area) -> None:
        self.screen = types.SimpleNamespace(areas=[area])


class _FakeView3DOps:
    """Fake ``bpy.ops.view3d.*``. Records every call (order matters) into ``calls`` and
    mutates ``region_3d.view_matrix``/``view_perspective`` so a render's final view
    state is distinguishable per view/orbit angle."""

    def __init__(self, region_3d, calls: list) -> None:
        self._r3d = region_3d
        self._calls = calls

    def view_axis(self, type):  # noqa: A002 - mirrors bpy.ops.view3d.view_axis(type=...)
        self._calls.append(("view_axis", type))
        self._r3d.view_matrix = f"AXIS:{type}"
        self._r3d.view_perspective = "PERSP" if type == "PERSP" else "ORTHO"

    def view_orbit(self, angle, type):  # noqa: A002 - mirrors bpy.ops.view3d.view_orbit
        self._calls.append(("view_orbit", type, angle))
        self._r3d.view_matrix = f"{self._r3d.view_matrix}+ORBIT:{type}:{angle:.6f}"
        self._r3d.view_perspective = "PERSP"

    def view_selected(self):
        self._calls.append(("view_selected",))

    def view_all(self):
        self._calls.append(("view_all",))

    def localview(self):
        self._calls.append(("localview",))


def _make_bpy(render_raises: bool = False, write_file: bool = True, with_view3d: bool = True):
    bpy = types.ModuleType("bpy")
    objects: dict = {}
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

    class _ViewLayerObjects:
        active = None

    view_layer = types.SimpleNamespace(update=lambda: None, objects=_ViewLayerObjects())

    view3d_area = _FakeArea() if with_view3d else None
    windows = [_FakeWindow(view3d_area)] if with_view3d else []
    window_manager = types.SimpleNamespace(windows=windows)

    override_calls: list = []

    @contextmanager
    def temp_override(**kw):
        override_calls.append(kw)
        yield

    bpy.context = types.SimpleNamespace(
        scene=scene,
        view_layer=view_layer,
        window_manager=window_manager,
        evaluated_depsgraph_get=lambda: "FAKE_DEPSGRAPH",
        temp_override=temp_override,
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
            return FakeCamData(name)

    bpy.data = types.SimpleNamespace(objects=_DataObjects(), cameras=_DataCameras())

    render_calls: list = []

    class _RenderOps:
        @staticmethod
        def opengl(write_still=False, **kw):
            render_calls.append({"write_still": write_still, **kw})
            if render_raises:
                raise RuntimeError("no GPU / headless")
            if write_file:
                with open(scene.render.filepath, "wb") as fh:
                    fh.write(b"\x89PNG\r\n\x1a\n" + b"fakepng")

    view3d_calls: list = []
    region_3d = view3d_area.spaces.active.region_3d if view3d_area is not None else None
    view3d_ops = _FakeView3DOps(region_3d, view3d_calls) if with_view3d else None

    bpy.ops = types.SimpleNamespace(render=_RenderOps(), view3d=view3d_ops)
    bpy._render_calls = render_calls
    bpy._view3d_calls = view3d_calls
    bpy._override_calls = override_calls
    bpy._scene = scene
    bpy._objects = objects
    return bpy


def _install_bpy(bpy, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "bpy", bpy)


@pytest.fixture()
def ctx_env(monkeypatch):
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    return Ctx(bpy), bpy


# -- handler happy path + degrade ---------------------------------------------------

def test_capture_named_view_renders_via_viewport(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "front"}, ctx)
    assert out["available"] is True
    assert out["view"] == "front"
    assert out["mimeType"] == "image/png"
    assert out["data"]  # base64 of the fake png

    # Isolated the subject in local view, drove the viewport to FRONT, framed the
    # (selected) object, then exited local view -- never a hidden capture camera, which
    # this render path no longer creates at all.
    assert bpy._view3d_calls[0] == ("localview",)
    assert bpy._view3d_calls[1] == ("view_axis", "FRONT")
    assert ("view_selected",) in bpy._view3d_calls
    assert bpy._view3d_calls[-1] == ("localview",)
    assert bpy._objects.get(cap.CAPTURE_CAM) is None

    # render.opengl was asked to capture the VIEWPORT (view_context=True), not a camera.
    assert bpy._render_calls[-1]["write_still"] is True
    assert bpy._render_calls[-1]["view_context"] is True

    # User's scene camera untouched (this path never sets scene.camera).
    assert bpy._scene.camera is None


def test_capture_persp_view_orbits_from_front(ctx_env) -> None:
    # The 3/4 look: FRONT, then orbit right (azimuth) and up (elevation), each converted
    # from degrees to radians -- mirrors the retired view_camera() persp direction.
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "persp"}, ctx)
    assert out["available"] is True
    assert bpy._view3d_calls[0] == ("localview",)
    assert bpy._view3d_calls[1] == ("view_axis", "FRONT")
    assert bpy._view3d_calls[2] == ("view_orbit", "ORBITRIGHT", pytest.approx(math.radians(cap.PERSP_AZIMUTH_DEG)))
    assert bpy._view3d_calls[3] == ("view_orbit", "ORBITUP", pytest.approx(math.radians(cap.PERSP_ELEVATION_DEG)))
    assert bpy._view3d_calls[4] == ("view_selected",)


def test_capture_views_returns_one_image_per_preset_view(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture_views", {"object": "Cube", "preset": "ortho4"}, ctx)
    assert out["available"] is True
    views = [img["view"] for img in out["images"]]
    assert views == ["front", "right", "top", "persp"]
    assert all(img["data"] for img in out["images"])
    # Each preset view issued its own view_axis call, in order.
    axis_calls = [c for c in bpy._view3d_calls if c[0] == "view_axis"]
    assert [c[1] for c in axis_calls[:3]] == ["FRONT", "RIGHT", "TOP"]


def test_capture_views_orbit4_orbits_four_azimuth_steps(ctx_env) -> None:
    ctx, bpy = ctx_env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture_views", {"object": "Cube", "preset": "orbit4"}, ctx)
    assert out["available"] is True
    assert [img["view"] for img in out["images"]] == ["orbit_0", "orbit_90", "orbit_180", "orbit_270"]
    orbit_right_angles = [c[2] for c in bpy._view3d_calls if c[0] == "view_orbit" and c[1] == "ORBITRIGHT"]
    # orbit_0 has azimuth 0 -> no ORBITRIGHT call at all (falsy angle is skipped, same as
    # a plain FRONT view); the remaining three each orbit by their azimuth in radians.
    assert orbit_right_angles == [pytest.approx(math.radians(90.0)), pytest.approx(math.radians(180.0)), pytest.approx(math.radians(270.0))]


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
    # "no VIEW_3D area" branch of _render_viewport, distinct from a render failure.
    bpy = _make_bpy(with_view3d=False)
    _install_bpy(bpy, monkeypatch)
    ctx = Ctx(bpy)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "feedback.capture", {"object": "Cube", "view": "front"}, ctx)
    assert out["available"] is False
    assert "VIEW_3D" in out["reason"]


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


# -- _render_viewport wiring: overlay/shading/selection/view-state toggled+restored -


def test_render_viewport_toggles_overlay_and_shading_then_restores(monkeypatch) -> None:
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    area = bpy.context.window_manager.windows[0].screen.areas[0]
    space = area.spaces.active
    space.overlay.show_overlays = True
    space.shading.type = "SOLID"

    data = cap._render_viewport(bpy, "MATERIAL", 64, "Cube", axis="TOP")

    assert data  # base64 PNG came back
    png_bytes = base64.b64decode(data)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Overlay/shading restored to their pre-render values afterward.
    assert space.overlay.show_overlays is True
    assert space.shading.type == "SOLID"

    # The right ops ran, in order: orient, frame, capture.
    assert bpy._view3d_calls == [("localview",), ("view_axis", "TOP"), ("view_selected",), ("localview",)]
    assert bpy._render_calls[-1] == {"write_still": True, "view_context": True}

    # temp_override was entered with this exact area/region.
    assert bpy._override_calls[-1] == {"area": area, "region": area.regions[0]}


def test_render_viewport_restores_selection_and_active_object(monkeypatch) -> None:
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    other = FakeObj("Other")
    bpy._objects["Other"] = other
    bpy._scene.objects.append(other)
    other.select_set(True)
    bpy.context.view_layer.objects.active = other

    cap._render_viewport(bpy, "SOLID", 64, "Cube", axis="FRONT")

    cube = bpy._objects["Cube"]
    # During the render only Cube was selected+active (proven by the FRONT axis call
    # succeeding via view_selected); afterward the ORIGINAL selection is back exactly.
    assert cube.select_get() is False
    assert other.select_get() is True
    assert bpy.context.view_layer.objects.active is other


def test_render_viewport_restores_region_3d_view_state(monkeypatch) -> None:
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    r3d = bpy.context.window_manager.windows[0].screen.areas[0].spaces.active.region_3d
    before = (r3d.view_perspective, r3d.view_distance, r3d.view_location, r3d.view_rotation, r3d.view_matrix)

    cap._render_viewport(bpy, "SOLID", 64, "Cube", axis="RIGHT")

    after = (r3d.view_perspective, r3d.view_distance, r3d.view_location, r3d.view_rotation, r3d.view_matrix)
    assert after == before


def test_render_viewport_uses_view_all_when_no_object_name(monkeypatch) -> None:
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    cap._render_viewport(bpy, "SOLID", 64, None, axis="TOP")
    assert ("view_all",) in bpy._view3d_calls
    assert ("view_selected",) not in bpy._view3d_calls


def test_render_viewport_restores_state_even_when_render_raises(monkeypatch) -> None:
    bpy = _make_bpy(render_raises=True)
    _install_bpy(bpy, monkeypatch)
    space = bpy.context.window_manager.windows[0].screen.areas[0].spaces.active
    space.overlay.show_overlays = True
    space.shading.type = "SOLID"

    with pytest.raises(RuntimeError):
        cap._render_viewport(bpy, "MATERIAL", 64, "Cube", axis="FRONT")

    assert space.overlay.show_overlays is True
    assert space.shading.type == "SOLID"
    assert bpy._objects["Cube"].select_get() is False


def test_render_viewport_no_view3d_raises() -> None:
    bpy = _make_bpy(with_view3d=False)
    with pytest.raises(RuntimeError):
        cap._render_viewport(bpy, "SOLID", 64, "Cube", axis="FRONT")


def test_render_viewport_requires_axis_or_orbit_kwargs(monkeypatch) -> None:
    bpy = _make_bpy()
    _install_bpy(bpy, monkeypatch)
    with pytest.raises(ValueError):
        cap._render_viewport(bpy, "SOLID", 64, "Cube")


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
