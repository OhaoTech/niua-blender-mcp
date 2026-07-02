"""Silhouette core render/restore unit tests (fake-bpy).

Mirrors the fake-bpy patterns already used in the repo: the object/render plumbing from
``tests/domains/test_feedback.py`` (bound_box + matrix_world + a fake VIEW_3D window/area
with view3d.*/render.opengl ops so ``core.capture._render_viewport`` can drive the "live"
viewport headless) and the material/node-tree plumbing from ``tests/domains/
test_shading.py`` (materials with a node_tree whose nodes carry named ``inputs``/
``outputs`` sockets, so the flat EMISSION fill material can be built exactly like
``core/overlay.py`` does).
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.core import silhouette


# -- fake bpy: object/render plumbing (from tests/domains/test_feedback.py) ---------


class _Mat:
    """4x4 identity-ish matrix supporting ``@ seq`` -> translated tuple (no rotation)."""

    def __init__(self, offset=(0.0, 0.0, 0.0)) -> None:
        self.offset = offset

    def __matmul__(self, vec):
        return tuple(vec[i] + self.offset[i] for i in range(3))


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
    def __init__(self) -> None:
        self.type = "VIEW_3D"
        self.spaces = types.SimpleNamespace(active=_FakeView3DSpace())
        self.regions = [_FakeRegion()]


class _FakeWindow:
    def __init__(self, area) -> None:
        self.screen = types.SimpleNamespace(areas=[area])


class _FakeWindowManager:
    def __init__(self, area, with_view3d: bool = True) -> None:
        self.windows = [_FakeWindow(area)] if with_view3d else []


class _FakeView3DOps:
    """Fake ``bpy.ops.view3d.*``: records every call, mutates ``region_3d.view_matrix``
    so a render's final view state is distinguishable per view/orbit angle."""

    def __init__(self, region_3d, calls: list) -> None:
        self._r3d = region_3d
        self._calls = calls

    def view_axis(self, type):  # noqa: A002
        self._calls.append(("view_axis", type))
        self._r3d.view_matrix = f"AXIS:{type}"

    def view_orbit(self, angle, type):  # noqa: A002
        self._calls.append(("view_orbit", type, angle))
        self._r3d.view_matrix = f"{self._r3d.view_matrix}+ORBIT:{type}:{angle:.6f}"

    def view_selected(self):
        self._calls.append(("view_selected",))

    def view_all(self):
        self._calls.append(("view_all",))


# -- fake bpy: material/node-tree plumbing (from tests/domains/test_shading.py) -----


class FakeSocket:
    def __init__(self, name: str = "") -> None:
        self.name = name
        self.default_value = None


class FakeNode:
    def __init__(self, ntype: str) -> None:
        self.type = ntype
        self.bl_idname = ntype
        if ntype == "ShaderNodeOutputMaterial":
            self.inputs = {"Surface": FakeSocket("Surface")}
            self.outputs: dict = {}
        elif ntype == "ShaderNodeEmission":
            self.inputs = {"Color": FakeSocket("Color"), "Strength": FakeSocket("Strength")}
            self.outputs = {"Emission": FakeSocket("Emission")}
        else:
            self.inputs = {}
            self.outputs = {}


class FakeNodes(list):
    def new(self, ntype: str) -> FakeNode:
        node = FakeNode(ntype)
        self.append(node)
        return node
    # .clear() is inherited from list -- matches nt.nodes.clear() in core/overlay.py.


class FakeLinks:
    def __init__(self) -> None:
        self.created: list = []

    def new(self, output_socket, input_socket):
        self.created.append((output_socket, input_socket))
        return object()


class FakeNodeTree:
    def __init__(self) -> None:
        self.nodes = FakeNodes()
        self.links = FakeLinks()


class FakeMaterial:
    def __init__(self, name: str) -> None:
        self.name = name
        self.node_tree = FakeNodeTree()
        self.diffuse_color = None
        self._use_nodes = False

    @property
    def use_nodes(self) -> bool:
        return self._use_nodes

    @use_nodes.setter
    def use_nodes(self, value: bool) -> None:
        self._use_nodes = bool(value)


# -- fake bpy: mesh object with material slots + per-polygon material_index ---------


class FakeSlot:
    def __init__(self, material) -> None:
        self.material = material


class FakePoly:
    def __init__(self, material_index: int = 0) -> None:
        self.material_index = material_index


class FakeMeshData:
    def __init__(self, materials, polygons) -> None:
        self.materials = list(materials)
        self.polygons = polygons


class FakeMeshObj:
    def __init__(self, name: str, materials, polygons) -> None:
        self.name = name
        self.type = "MESH"
        self.matrix_world = _Mat()
        # Unit cube centered at origin (mirrors FakeObj.bound_box in test_feedback.py).
        self.bound_box = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
        ]
        self.data = FakeMeshData(materials, polygons)
        self._selected = False

    @property
    def material_slots(self):
        return [FakeSlot(m) for m in self.data.materials]

    def select_get(self) -> bool:
        return self._selected

    def select_set(self, value) -> None:
        self._selected = bool(value)


def _make_bpy(mesh_obj, render_raises: bool = False, with_view3d: bool = True):
    bpy = types.ModuleType("bpy")
    objects: dict = {mesh_obj.name: mesh_obj}
    materials: dict = {}
    scene_objs: list = [mesh_obj]

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
    area = _FakeArea() if with_view3d else None
    window_manager = _FakeWindowManager(area, with_view3d=with_view3d)

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

    class _DataMaterials:
        @staticmethod
        def get(name):
            return materials.get(name)

        @staticmethod
        def new(name):
            mat = FakeMaterial(name)
            materials[name] = mat
            return mat

    bpy.data = types.SimpleNamespace(
        objects=_DataObjects(),
        materials=_DataMaterials(),
    )

    render_calls: list = []

    class _RenderOps:
        @staticmethod
        def opengl(write_still=False, **kw):
            render_calls.append({"write_still": write_still, **kw})
            if render_raises:
                raise RuntimeError("no GPU / headless")
            with open(scene.render.filepath, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"fakepng")

    view3d_calls: list = []
    view3d_ops = _FakeView3DOps(area.spaces.active.region_3d, view3d_calls) if with_view3d else None

    bpy.ops = types.SimpleNamespace(render=_RenderOps(), view3d=view3d_ops)
    bpy._render_calls = render_calls
    bpy._view3d_calls = view3d_calls
    bpy._override_calls = override_calls
    bpy._objects = objects
    bpy._materials = materials
    return bpy


def _install_bpy(bpy, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "bpy", bpy)


@pytest.fixture()
def fake_bpy_recording_mesh(monkeypatch):
    """A fake bpy exposing one mesh object ('Cube') with 2 material slots and 6 faces
    split across both slots. Mirrors the object the plan's test drives
    ``silhouette.render_silhouette`` against.
    """
    orig_mat_a = FakeMaterial("OrigA")
    orig_mat_b = FakeMaterial("OrigB")
    polygons = [FakePoly(i % 2) for i in range(6)]
    mesh_obj = FakeMeshObj("Cube", materials=[orig_mat_a, orig_mat_b], polygons=polygons)
    bpy = _make_bpy(mesh_obj)
    _install_bpy(bpy, monkeypatch)
    return bpy


def test_render_silhouette_assigns_flat_fill_and_restores(fake_bpy_recording_mesh):
    bpy = fake_bpy_recording_mesh
    obj = bpy.data.objects.get("Cube")
    before_slots = [s.material for s in obj.material_slots]
    before_idx = [p.material_index for p in obj.data.polygons]

    out = silhouette.render_silhouette(bpy, "Cube", preset="ortho4", res=256)

    assert out["available"] is True
    assert out["preset"] == "ortho4"
    assert out["images"] and all(im["mode"] == "silhouette" for im in out["images"])
    # one image per ortho4 view
    assert {im["view"] for im in out["images"]} == {"front", "right", "top", "persp"}
    # materials + indices restored byte-identical
    assert [s.material for s in obj.material_slots] == before_slots
    assert [p.material_index for p in obj.data.polygons] == before_idx
    # Selection was cleared again after framing (non-intrusive).
    assert obj.select_get() is False


def test_render_silhouette_views_get_distinct_viewport_orientations(fake_bpy_recording_mesh):
    # The anti-blob check: each ortho4 view must drive the viewport to a genuinely
    # different bpy.ops.view3d.view_axis type (or orbit) -- never a shared/stale one --
    # the class of bug docs/reports/capture-multiangle-bug.md fixed.
    bpy = fake_bpy_recording_mesh
    out = silhouette.render_silhouette(bpy, "Cube", preset="ortho4", res=256)
    assert out["available"] is True
    axis_calls = [c for c in bpy._view3d_calls if c[0] == "view_axis"]
    # front, right, top axes, then persp's FRONT-then-orbit look.
    assert [c[1] for c in axis_calls] == ["FRONT", "RIGHT", "TOP", "FRONT"]
    orbit_calls = [c for c in bpy._view3d_calls if c[0] == "view_orbit"]
    assert len(orbit_calls) == 2  # persp: one ORBITRIGHT + one ORBITUP
    # Every render actually captured the viewport, not a positioned camera.
    assert len(bpy._render_calls) == 4
    assert all(call["view_context"] is True for call in bpy._render_calls)
    # MATERIAL shading (for the flat emission fill) was active during every render.
    assert bpy.context.window_manager.windows[0].screen.areas[0].spaces.active.shading.type == "SOLID"


def test_render_silhouette_restores_materials_even_when_render_fails(monkeypatch):
    orig_mat_a = FakeMaterial("OrigA")
    orig_mat_b = FakeMaterial("OrigB")
    polygons = [FakePoly(i % 2) for i in range(6)]
    mesh_obj = FakeMeshObj("Cube", materials=[orig_mat_a, orig_mat_b], polygons=polygons)
    bpy = _make_bpy(mesh_obj, render_raises=True)
    _install_bpy(bpy, monkeypatch)
    obj = bpy.data.objects.get("Cube")
    before_slots = [s.material for s in obj.material_slots]
    before_idx = [p.material_index for p in obj.data.polygons]

    out = silhouette.render_silhouette(bpy, "Cube", preset="ortho4", res=256)

    assert out["available"] is False
    assert "reason" in out
    assert [s.material for s in obj.material_slots] == before_slots
    assert [p.material_index for p in obj.data.polygons] == before_idx


def test_render_silhouette_degrades_with_no_view3d_area(monkeypatch):
    orig_mat_a = FakeMaterial("OrigA")
    polygons = [FakePoly(0) for _ in range(6)]
    mesh_obj = FakeMeshObj("Cube", materials=[orig_mat_a], polygons=polygons)
    bpy = _make_bpy(mesh_obj, with_view3d=False)
    _install_bpy(bpy, monkeypatch)

    out = silhouette.render_silhouette(bpy, "Cube", preset="ortho4", res=256)

    assert out["available"] is False
    assert "VIEW_3D" in out["reason"]


def test_render_silhouette_non_mesh_degrades():
    class _Empty:
        type = "EMPTY"

    class _BpyNoMesh:
        class data:
            class objects:
                @staticmethod
                def get(_n):
                    return _Empty()

    out = silhouette.render_silhouette(_BpyNoMesh, "X")
    assert out["available"] is False and "reason" in out
