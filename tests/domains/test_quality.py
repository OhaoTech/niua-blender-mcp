"""feedback.quality unit tests (fake-bpy).

A fake mesh with known vertex coordinates and faces drives the pure-geometry metrics:
topology counts / ratios, symmetry across each local plane (symmetric vs lopsided mesh),
and proportion. bmesh is absent in this env, so pole_count / non_manifold_edges /
loose_verts degrade to ``null`` (asserted) while every pure-Python field still computes.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import PRECONDITION, BridgeError


def _identity() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class FakeVert:
    def __init__(self, co) -> None:
        self.co = tuple(float(c) for c in co)


class FakePoly:
    def __init__(self, vert_indices) -> None:
        self.vertices = list(vert_indices)


class FakeMesh:
    def __init__(self, *, verts=None, polys=None, edges=0, uv_layers=0, materials=0) -> None:
        self.vertices = [FakeVert(c) for c in (verts or [])]
        self.edges = [object() for _ in range(edges)]
        self.polygons = [FakePoly(p) for p in (polys or [])]
        self.uv_layers = [object() for _ in range(uv_layers)]
        self.materials = [object() for _ in range(materials)]


class FakeObj:
    def __init__(self, name, type="MESH", data=None, dimensions=(2.0, 2.0, 2.0)) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeMesh()
        self.dimensions = list(dimensions)
        self.matrix_world = _identity()


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active = None
        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active

            @active.setter
            def active(self_inner, value):
                bpy._active = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        class _Context:
            scene = self.scene
            view_layer = self.view_layer
            window_manager = types.SimpleNamespace(windows=[])

            @property
            def object(self_inner):
                return bpy._active

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()
        self.ops = types.SimpleNamespace(
            ed=types.SimpleNamespace(undo_push=lambda **kw: None, undo=lambda **kw: None)
        )

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        self._active = obj
        return obj

    @property
    def data(self):
        store = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.delitem(sys.modules, "bmesh", raising=False)
    return Ctx(bpy), bpy


# A small symmetric "box-ish" patch: every vert has its X-mirror partner.
_SYMMETRIC_VERTS = [
    (-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0),  # quad on z=0
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),  # quad on z=1
]
_SYMMETRIC_POLYS = [[0, 1, 2, 3], [4, 5, 6, 7]]  # two quads


def _quality(env, name, **payload):
    ctx, bpy = env
    reg = build_default_registry()
    return dispatch_on_main(reg, "feedback.quality", {"object": name, **payload}, ctx)


def test_topology_ratios_quads_tris_ngons(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(
        verts=_SYMMETRIC_VERTS,
        # 2 quads + 1 tri + 1 pentagon(ngon)
        polys=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 2], [0, 1, 2, 3, 4]],
    )
    bpy.add(FakeObj("Cube", data=mesh))
    q = _quality(env, "Cube")["topology"]
    assert q["faces"] == 4
    assert q["quads"] == 2
    assert q["ngons"] == 1
    # tris (triangulated): quad=2,quad=2,tri=1,pentagon=3 -> 8
    assert q["tris"] == 8
    assert q["quad_ratio"] == pytest.approx(0.5)
    assert q["ngon_ratio"] == pytest.approx(0.25)


def test_bmesh_fields_degrade_to_null_without_bmesh(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    q = _quality(env, "Cube")["topology"]
    assert q["pole_count"] is None
    assert q["non_manifold_edges"] is None
    assert q["loose_verts"] is None


def test_symmetric_mesh_is_symmetric_on_all_axes(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    sym = _quality(env, "Cube")["symmetry"]
    # X and Y mirror partners exist for every vert.
    assert sym["symmetry_x"] == pytest.approx(1.0)
    assert sym["symmetry_y"] == pytest.approx(1.0)
    # Z: z=0 and z=1 are NOT mirror images across z=0, so this is < 1.0 (only the z=0 ring
    # self-mirrors). The point: the metric distinguishes axes.
    assert sym["symmetry_z"] < 1.0


def test_lopsided_mesh_has_low_x_symmetry(env) -> None:
    ctx, bpy = env
    # Shove the +X verts outward only on the right: no left partner for them.
    lopsided = [
        (-1, -1, 0), (5, -1, 0), (5, 1, 0), (-1, 1, 0),
        (-1, -1, 1), (5, -1, 1), (5, 1, 1), (-1, 1, 1),
    ]
    bpy.add(FakeObj("Lop", data=FakeMesh(verts=lopsided, polys=_SYMMETRIC_POLYS)))
    sym = _quality(env, "Lop")["symmetry"]
    assert sym["symmetry_x"] < 1.0  # lopsided across YZ plane
    assert sym["symmetry_y"] == pytest.approx(1.0)  # still mirrored in Y


def test_proportion_and_scale_blocks(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS),
                  dimensions=(4.0, 2.0, 1.0))
    bpy.add(obj)
    out = _quality(env, "Cube")
    prop = out["proportion"]
    assert prop["bbox_dimensions"] == [4.0, 2.0, 1.0]
    assert prop["aspect_ratio"] == pytest.approx(4.0)  # longest/shortest = 4/1
    assert prop["boxiness"] is not None
    scale = out["scale"]
    assert scale["bbox_dimensions"] == [4.0, 2.0, 1.0]
    assert scale["transform_applied"] is True  # identity matrix_world


def test_quality_includes_uv_block_with_fake_bpy_degrade(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS, uv_layers=1)))
    out = _quality(env, "Cube")
    assert out["uv"]["has_uvs"] is True
    assert out["uv"]["uv_layer_count"] == 1
    assert out["uv"]["texel_density_px_per_unit"] is None


def test_quality_is_read_only_no_undo(env) -> None:
    ctx, bpy = env
    pushes: list = []
    bpy.ops.ed.undo_push = lambda **kw: pushes.append(kw)
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    _quality(env, "Cube")
    assert pushes == []


def test_quality_non_mesh_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Lamp", type="LIGHT", data=FakeMesh()))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "feedback.quality", {"object": "Lamp"}, ctx)
    assert exc.value.code == PRECONDITION
