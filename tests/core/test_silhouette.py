"""Silhouette core render/restore unit tests (fake-bpy).

Mirrors the fake-bpy patterns already used in the repo: the object/camera/render
plumbing from ``tests/domains/test_feedback.py`` (bound_box + matrix_world + a fake
``gpu`` module + fake VIEW_3D window/area so ``core.capture._render_offscreen`` can
run headless -- see that file's comment on why ``gpu`` must be faked, not just
``bpy``) and the material/node-tree plumbing from ``tests/domains/test_shading.py``
(materials with a node_tree whose nodes carry named ``inputs``/``outputs`` sockets, so
the flat EMISSION fill material can be built exactly like ``core/overlay.py`` does).
"""

from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.core import silhouette


# -- fake bpy: object/camera/render plumbing (from tests/domains/test_feedback.py) --


class _Mat:
    """4x4 identity-ish matrix supporting ``@ seq`` -> translated tuple (no rotation)."""

    def __init__(self, offset=(0.0, 0.0, 0.0)) -> None:
        self.offset = offset

    def __matmul__(self, vec):
        return tuple(vec[i] + self.offset[i] for i in range(3))


class FakeCamData:
    def __init__(self, name) -> None:
        self.name = name
        self.type = "PERSP"
        self.ortho_scale = 1.0


class FakeCamObj:
    def __init__(self, name, data) -> None:
        self.name = name
        self.type = "CAMERA"
        self.data = data
        self.location = (0.0, 0.0, 0.0)
        self.rotation_mode = "XYZ"
        self.rotation_euler = (0.0, 0.0, 0.0)
        self.hide_viewport = False
        self.hide_render = False

    def calc_matrix_camera(self, depsgraph, x=1, y=1, scale_x=1.0, scale_y=1.0):
        # See tests/domains/test_feedback.py::FakeObj.calc_matrix_camera -- a sentinel
        # is enough since the fake draw_view3d below only records it.
        return ("FAKE_PROJ_MATRIX", self.name, getattr(self.data, "type", None), x, y)


# -- fake gpu module + fake VIEW_3D window/area (from tests/domains/test_feedback.py) --


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
    draw_calls: list = []

    class _FakeGPUOffScreen:
        def __init__(self, width, height):
            self.width = width
            self.height = height

        def draw_view3d(self, scene, view_layer, space, region, view_matrix, proj_matrix, do_color_management=False):
            draw_calls.append(
                {
                    "space": space,
                    "view_matrix": view_matrix,
                    "proj_matrix": proj_matrix,
                    "shading_type": getattr(space.shading, "type", None),
                    "overlay_show_overlays": getattr(space.overlay, "show_overlays", None),
                }
            )
            if draw_raises:
                raise RuntimeError("no GPU / headless")

        def bind(self):
            return _NullBind()

        def free(self):
            pass

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
    def __init__(self) -> None:
        self.type = "VIEW_3D"
        self.spaces = types.SimpleNamespace(active=_FakeView3DSpace())
        self.regions = [_FakeRegion()]


class _FakeScreen:
    def __init__(self) -> None:
        self.areas = [_FakeArea()]


class _FakeWindow:
    def __init__(self) -> None:
        self.screen = _FakeScreen()


class _FakeWindowManager:
    def __init__(self) -> None:
        self.windows = [_FakeWindow()]


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

    @property
    def material_slots(self):
        return [FakeSlot(m) for m in self.data.materials]


def _make_bpy(mesh_obj, draw_raises: bool = False):
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
    bpy.context = types.SimpleNamespace(
        scene=scene,
        view_layer=types.SimpleNamespace(update=lambda: None),
        window_manager=_FakeWindowManager(),
        evaluated_depsgraph_get=lambda: "FAKE_DEPSGRAPH",
    )

    class _DataObjects:
        @staticmethod
        def get(name):
            return objects.get(name)

        @staticmethod
        def new(name, data):
            return FakeCamObj(name, data)

    class _DataCameras:
        @staticmethod
        def new(name):
            return FakeCamData(name)

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
        cameras=_DataCameras(),
        materials=_DataMaterials(),
    )

    render_calls: list = []

    class _RenderOps:
        @staticmethod
        def opengl(write_still=False, **kw):
            render_calls.append(write_still)
            with open(scene.render.filepath, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"fakepng")

    bpy.ops = types.SimpleNamespace(render=_RenderOps())
    bpy._render_calls = render_calls
    bpy._objects = objects
    bpy._materials = materials
    gpu_module, gpu_draw_calls = _make_fake_gpu(draw_raises=draw_raises)
    bpy._gpu_module = gpu_module
    bpy._gpu_draw_calls = gpu_draw_calls
    return bpy


def _install_bpy(bpy, monkeypatch) -> None:
    """Inject the fake ``bpy`` AND its matching fake ``gpu`` into sys.modules -- see
    tests/domains/test_feedback.py::_install_bpy for why both are needed."""
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setitem(sys.modules, "gpu", bpy._gpu_module)


@pytest.fixture()
def fake_bpy_recording_mesh(monkeypatch):
    """A fake bpy exposing one mesh object ('Cube') with 2 material slots and 6 faces
    split across both slots, plus a fake ``gpu`` module (installed into sys.modules).
    Mirrors the object the plan's test drives ``silhouette.render_silhouette`` against.
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


def test_render_silhouette_views_get_distinct_view_matrices(fake_bpy_recording_mesh):
    # The anti-blob check: each ortho4 view must reach _render_offscreen with a
    # genuinely different pure-python view matrix (never a shared/stale one) -- the
    # class of bug docs/reports/capture-multiangle-bug.md fixed.
    bpy = fake_bpy_recording_mesh
    out = silhouette.render_silhouette(bpy, "Cube", preset="ortho4", res=256)
    assert out["available"] is True
    assert len(bpy._gpu_draw_calls) == 4
    matrices = [call["view_matrix"] for call in bpy._gpu_draw_calls]
    flat = [tuple(v for row in m for v in row) for m in matrices]
    assert len(set(flat)) == 4  # all four distinct
    # MATERIAL shading (for the flat emission fill) was active during every render.
    assert all(call["shading_type"] == "MATERIAL" for call in bpy._gpu_draw_calls)
    assert all(call["overlay_show_overlays"] is False for call in bpy._gpu_draw_calls)


def test_render_silhouette_restores_materials_even_when_render_fails(monkeypatch):
    orig_mat_a = FakeMaterial("OrigA")
    orig_mat_b = FakeMaterial("OrigB")
    polygons = [FakePoly(i % 2) for i in range(6)]
    mesh_obj = FakeMeshObj("Cube", materials=[orig_mat_a, orig_mat_b], polygons=polygons)
    bpy = _make_bpy(mesh_obj, draw_raises=True)
    _install_bpy(bpy, monkeypatch)
    obj = bpy.data.objects.get("Cube")
    before_slots = [s.material for s in obj.material_slots]
    before_idx = [p.material_index for p in obj.data.polygons]

    out = silhouette.render_silhouette(bpy, "Cube", preset="ortho4", res=256)

    assert out["available"] is False
    assert "reason" in out
    assert [s.material for s in obj.material_slots] == before_slots
    assert [p.material_index for p in obj.data.polygons] == before_idx


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
