from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.domains import capabilities as cap


class FakeProp:
    def __init__(self, identifier: str, type: str = "FLOAT") -> None:
        self.identifier = identifier
        self.type = type


class FakeRnaType:
    def __init__(self, description: str, bl_label: str = "", props: list[FakeProp] | None = None) -> None:
        self.description = description
        self.bl_label = bl_label
        self.properties = props or []


class FakeOp:
    def __init__(self, log: list, name: str, rna: FakeRnaType) -> None:
        self._log = log
        self._name = name
        self._rna = rna

    def get_rna_type(self) -> FakeRnaType:
        return self._rna

    def poll(self) -> bool:
        return True

    def __call__(self, **kwargs) -> None:
        self._log.append((self._name, kwargs))


class FakeObj:
    def __init__(self, name: str) -> None:
        self.name = name
        self.type = "MESH"
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active_obj = None

        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

            @active.setter
            def active(self_inner, value):
                bpy._active_obj = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        class _Context:
            scene = self.scene
            view_layer = self.view_layer
            window_manager = types.SimpleNamespace(windows=[])

            @property
            def object(self_inner):
                return bpy._active_obj

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()

        class _MeshOps:
            subdivide = FakeOp(
                self.op_calls,
                "mesh.subdivide",
                FakeRnaType("Subdivide selected edges", "Subdivide", [FakeProp("number_cuts", "INT")]),
            )

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw) -> None:
                bpy.undo_pushes.append(message)

        class _ObjectOps:
            def mode_set(self_inner, mode: str = "OBJECT", **kw) -> None:
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        self.ops = types.SimpleNamespace(mesh=_MeshOps(), object=_ObjectOps(), ed=_EdOps())
        self.types = types.SimpleNamespace()

    def add(self, obj: FakeObj) -> FakeObj:
        self.scene.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        bpy = self

        class _Objects:
            def get(self_inner, name):
                return next((obj for obj in bpy.scene.objects if obj.name == name), None)

        return types.SimpleNamespace(objects=_Objects())


def make_fake_bpy() -> FakeBpy:
    bpy = FakeBpy()
    bpy.add(FakeObj("Cube"))
    sys.modules["bpy"] = bpy
    return bpy


def test_search_delegates_to_live_rna() -> None:
    ctx = Ctx(make_fake_bpy())
    out = cap.search(ctx, {"query": "subdivide", "kind": "operator"})
    assert out["count"] >= 1
    assert any("subdivide" in m["idname"] for m in out["matches"])


def test_describe_returns_properties() -> None:
    ctx = Ctx(make_fake_bpy())
    out = cap.describe(ctx, {"id": "mesh.subdivide"})
    assert out["id"] == "mesh.subdivide"
    assert "properties" in out


def test_invoke_delegates_to_call_operator() -> None:
    ctx = Ctx(make_fake_bpy())
    out = cap.invoke(ctx, {"idname": "mesh.subdivide", "args": json.dumps({"number_cuts": 2})})
    assert out["operator"] == "mesh.subdivide"
