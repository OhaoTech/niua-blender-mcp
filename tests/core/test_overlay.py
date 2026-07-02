"""Topology overlay unit tests (fake-bpy).

Covers (1) ``face_type_groups`` (pure Python, no bpy) and (2) ``topology_overlay``'s
render path under a fake bpy -- mirroring the harness in tests/core/test_silhouette.py
(itself mirroring tests/domains/test_feedback.py): a fake VIEW_3D window/area with
view3d.*/render.opengl ops so ``core.capture._render_viewport`` can drive the "live"
viewport headless, plus the material/node-tree fakes from tests/domains/test_shading.py-
style tests so the flat EMISSION marker materials ``core/overlay.py`` builds actually
construct successfully.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.core.overlay import face_type_groups, topology_overlay


class _Poly:
    def __init__(self, index, sides):
        self.index = index
        self.vertices = list(range(sides))


def test_groups_faces_by_side_count():
    polys = [_Poly(0, 3), _Poly(1, 4), _Poly(2, 5), _Poly(3, 4)]
    groups = face_type_groups(polys)
    assert groups == {"tris": [0], "quads": [1, 3], "ngons": [2]}


def test_empty_mesh_groups_empty():
    assert face_type_groups([]) == {"tris": [], "quads": [], "ngons": []}


# -- fake bpy: object/render plumbing (mirrors tests/core/test_silhouette.py) --------


class _Mat:
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
    def __init__(self, area) -> None:
        self.windows = [_FakeWindow(area)]


class _FakeView3DOps:
    """Fake ``bpy.ops.view3d.*``: records every call, mutates ``region_3d.view_matrix``
    so a render's final view state is distinguishable per view."""

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


# -- fake bpy: material/node-tree plumbing --------------------------------------------


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


# -- fake bpy: mesh object with material slots + modifiers ----------------------------


class FakeSlot:
    def __init__(self, material) -> None:
        self.material = material


class FakePoly:
    def __init__(self, index: int, sides: int) -> None:
        self.index = index
        self.vertices = list(range(sides))
        self.material_index = 0


class FakeMeshData:
    def __init__(self, materials, polygons) -> None:
        self.materials = list(materials)
        self.polygons = polygons


class FakeModifier:
    def __init__(self, name: str, type: str) -> None:
        self.name = name
        self.type = type
        self.thickness = 0.0
        self.use_replace = True
        self.use_even_offset = False
        self.material_offset = 0


class FakeModifierStack(list):
    def new(self, name: str, type: str) -> FakeModifier:
        mod = FakeModifier(name, type)
        self.append(mod)
        return mod

    def remove(self, mod: FakeModifier) -> None:
        list.remove(self, mod)


class FakeMeshObj:
    def __init__(self, name: str, materials, polygons) -> None:
        self.name = name
        self.type = "MESH"
        self.matrix_world = _Mat()
        self.bound_box = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
        ]
        self.data = FakeMeshData(materials, polygons)
        self.modifiers = FakeModifierStack()
        self._selected = False

    @property
    def material_slots(self):
        return [FakeSlot(m) for m in self.data.materials]

    def select_get(self) -> bool:
        return self._selected

    def select_set(self, value) -> None:
        self._selected = bool(value)


def _make_bpy(mesh_obj, render_raises: bool = False):
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
    area = _FakeArea()
    window_manager = _FakeWindowManager(area)

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
    view3d_ops = _FakeView3DOps(area.spaces.active.region_3d, view3d_calls)

    bpy.ops = types.SimpleNamespace(render=_RenderOps(), view3d=view3d_ops)
    bpy._objects = objects
    bpy._materials = materials
    bpy._render_calls = render_calls
    bpy._view3d_calls = view3d_calls
    bpy._override_calls = override_calls
    return bpy


@pytest.fixture()
def fake_bpy_with_ngon(monkeypatch):
    """A quad, a tri, and an n-gon on one mesh."""
    mat_a = FakeMaterial("OrigA")
    polygons = [FakePoly(0, 4), FakePoly(1, 3), FakePoly(2, 5)]
    mesh_obj = FakeMeshObj("Shape", materials=[mat_a], polygons=polygons)
    bpy = _make_bpy(mesh_obj)
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return bpy


def test_topology_overlay_renders_two_passes_and_restores(fake_bpy_with_ngon):
    bpy = fake_bpy_with_ngon
    obj = bpy.data.objects.get("Shape")
    before_slots = [s.material for s in obj.material_slots]
    before_idx = [p.material_index for p in obj.data.polygons]

    out = topology_overlay(bpy, "Shape", view="persp", res=128)

    assert out["available"] is True
    assert out["groups"] == {"tris": 1, "quads": 1, "ngons": 1}
    assert len(out["images"]) == 2
    assert {im["mode"] for im in out["images"]} == {"facetype", "wireframe"}
    assert all(im["data"] for im in out["images"])

    # Mesh state (materials + indices) restored byte-identical.
    assert [s.material for s in obj.material_slots] == before_slots
    assert [p.material_index for p in obj.data.polygons] == before_idx
    # The temporary wireframe modifier was removed, not left behind.
    assert list(obj.modifiers) == []
    # Selection was cleared again after framing (non-intrusive).
    assert obj.select_get() is False

    # Two renders happened -- the SAME viewport orientation (persp) both times so the
    # only difference between the passes is the wireframe modifier added in between --
    # while render.opengl actually captured the viewport (view_context=True) twice.
    assert len(bpy._render_calls) == 2
    assert all(call["view_context"] is True for call in bpy._render_calls)
    axis_calls = [c for c in bpy._view3d_calls if c[0] == "view_axis"]
    assert len(axis_calls) == 2 and axis_calls[0] == axis_calls[1] == ("view_axis", "FRONT")


def test_topology_overlay_non_mesh_degrades():
    class _Empty:
        type = "EMPTY"

    class _BpyNoMesh:
        class data:
            class objects:
                @staticmethod
                def get(_n):
                    return _Empty()

    out = topology_overlay(_BpyNoMesh, "X")
    assert out["available"] is False and "reason" in out
