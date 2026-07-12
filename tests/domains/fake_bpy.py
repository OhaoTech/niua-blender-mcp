"""Shared fake-bpy env + cube mesh fixtures for domain tests.

Extracted from the deleted tests/domains/test_pipeline.py (Phase 3: the pipeline FSM
tool surface is gone, but the ruler tests -- test_readiness.py / test_preservation.py --
still exercise real geometry against a fake bpy and reuse these fixtures.

Note: "tests" has no __init__.py -- pytest's rootdir insertion makes this module
importable as "domains.fake_bpy", not "tests.domains.fake_bpy".
"""

from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.core import session as session_store


def _identity() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class FakeVert:
    def __init__(self, co) -> None:
        self.co = tuple(float(c) for c in co)


class FakePoly:
    def __init__(self, vert_indices) -> None:
        self.vertices = list(vert_indices)


class FakeMesh:
    def __init__(self, *, verts=None, polys=None, edges=0, uv_layers=0, materials=0, tag="mesh") -> None:
        self.vertices = [FakeVert(c) for c in (verts or [])]
        self.edges = [object() for _ in range(edges)]
        self.polygons = [FakePoly(p) for p in (polys or [])]
        self.uv_layers = [object() for _ in range(uv_layers)]
        self.materials = [object() for _ in range(materials)] if isinstance(materials, int) else list(materials)
        self.tag = tag

    def copy(self) -> "FakeMesh":
        return FakeMesh(
            verts=[vert.co for vert in self.vertices],
            polys=[poly.vertices for poly in self.polygons],
            edges=len(self.edges),
            uv_layers=len(self.uv_layers),
            materials=len(self.materials),
            tag=self.tag,
        )


class FakeObj:
    def __init__(self, name, type="MESH", data=None, dimensions=(2.0, 2.0, 2.0)) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeMesh()
        self.dimensions = list(dimensions)
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.matrix_world = _identity()


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active = None
        self.undo_pushes: list[str] = []
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

        self.context = _Context()

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(ed=_EdOps())

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
    session_store.reset()
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.delitem(sys.modules, "bmesh", raising=False)
    return Ctx(bpy), bpy


_CUBE_VERTS = [
    (-1, -1, -1),
    (1, -1, -1),
    (1, 1, -1),
    (-1, 1, -1),
    (-1, -1, 1),
    (1, -1, 1),
    (1, 1, 1),
    (-1, 1, 1),
]
_CUBE_QUADS = [
    [0, 1, 2, 3],
    [4, 5, 6, 7],
    [0, 1, 5, 4],
    [1, 2, 6, 5],
    [2, 3, 7, 6],
    [3, 0, 4, 7],
]
