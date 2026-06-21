"""Lattice GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import PRECONDITION, BridgeError


class FakeEnumItem:
    def __init__(self, identifier: str, name: str = "") -> None:
        self.identifier = identifier
        self.name = name or identifier.title()


class FakeRnaProp:
    def __init__(
        self,
        identifier: str,
        type: str,
        *,
        is_readonly: bool = False,
        is_array: bool = False,
        array_length: int = 0,
        enum_items: list[FakeEnumItem] | None = None,
    ) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = is_array
        self.array_length = array_length
        self.enum_items = list(enum_items or [])
        self.enum_items_static = list(enum_items or [])


class FakeRnaProperties(list):
    def get(self, identifier: str):
        return next((prop for prop in self if prop.identifier == identifier), None)

    def __getitem__(self, key):
        if isinstance(key, str):
            prop = self.get(key)
            if prop is None:
                raise KeyError(key)
            return prop
        return super().__getitem__(key)


def _rna(*props: FakeRnaProp):
    return types.SimpleNamespace(properties=FakeRnaProperties([FakeRnaProp("rna_type", "POINTER", is_readonly=True), *props]))


INTERPOLATION_ITEMS = [
    FakeEnumItem("KEY_LINEAR", "Linear"),
    FakeEnumItem("KEY_CARDINAL", "Cardinal"),
    FakeEnumItem("KEY_CATMULL_ROM", "Catmull-Rom"),
    FakeEnumItem("KEY_BSPLINE", "B-Spline"),
]


class FakeLatticePoint:
    def __init__(self, index: int) -> None:
        self.index = index
        self.select = False
        self.co = [-0.5, -0.5, -0.5]
        self.co_deform = [0.0, 0.0, 0.0]
        self.weight_softbody = 1.0
        self.groups = []
        self.bl_rna = _rna(
            FakeRnaProp("select", "BOOLEAN"),
            FakeRnaProp("co", "FLOAT", is_readonly=True, is_array=True, array_length=3),
            FakeRnaProp("co_deform", "FLOAT", is_array=True, array_length=3),
            FakeRnaProp("weight_softbody", "FLOAT"),
            FakeRnaProp("groups", "COLLECTION", is_readonly=True),
        )


class FakeLatticeData:
    def __init__(self, name: str = "Lattice") -> None:
        self.name = name
        self.points_u = 2
        self.points_v = 2
        self.points_w = 2
        self.interpolation_type_u = "KEY_BSPLINE"
        self.interpolation_type_v = "KEY_BSPLINE"
        self.interpolation_type_w = "KEY_BSPLINE"
        self.use_outside = False
        self.points = [FakeLatticePoint(index) for index in range(8)]
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("points_u", "INT"),
            FakeRnaProp("points_v", "INT"),
            FakeRnaProp("points_w", "INT"),
            FakeRnaProp("interpolation_type_u", "ENUM", enum_items=INTERPOLATION_ITEMS),
            FakeRnaProp("interpolation_type_v", "ENUM", enum_items=INTERPOLATION_ITEMS),
            FakeRnaProp("interpolation_type_w", "ENUM", enum_items=INTERPOLATION_ITEMS),
            FakeRnaProp("use_outside", "BOOLEAN"),
            FakeRnaProp("points", "COLLECTION", is_readonly=True),
        )


class FakeObj:
    def __init__(self, name: str, type: str = "LATTICE") -> None:
        self.name = name
        self.type = type
        self.data = FakeLatticeData(name)
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeObjects(list):
    def get(self, name: str):
        return next((obj for obj in self if obj.name == name), None)


class _Op:
    def __init__(self, log: list, name: str, on_call=None, poll_ok: bool = True) -> None:
        self._log = log
        self._name = name
        self._on_call = on_call
        self._poll_ok = poll_ok

    def poll(self) -> bool:
        return self._poll_ok

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))
        if self._on_call is not None:
            return self._on_call(**kwargs)
        return {"FINISHED"}


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = FakeObjects()
        self.op_calls: list = []
        self.mode_calls: list[str] = []
        self.undo_pushes: list[str] = []
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
        self.scene = types.SimpleNamespace(objects=self.objects, name="Scene")

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
        log = self.op_calls

        def _object_add(type: str = "EMPTY", location=None, **kwargs):
            obj = FakeObj("Lattice", type=type)
            obj.location = list(location or [0.0, 0.0, 0.0])
            self.add(obj)
            return {"FINISHED"}

        def _convert(**kwargs):
            return {"CANCELLED"}

        class _ObjectOps:
            add = _Op(log, "object.add", on_call=_object_add)
            convert = _Op(log, "object.convert", on_call=_convert)

            @staticmethod
            def mode_set(mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            @staticmethod
            def undo_push(message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(object=_ObjectOps(), ed=_EdOps())

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        return types.SimpleNamespace(objects=self.objects, materials={})


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _op_names(bpy: FakeBpy) -> list[str]:
    return [name for name, _ in bpy.op_calls]


def test_router_contains_lattice_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "lattice.create",
        "lattice.report",
        "lattice.set",
        "lattice.point_set",
        "lattice.convert_to_mesh",
    } <= names


def test_create_report_set_and_point_set_lattice(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(reg, "lattice.create", {"name": "Cage", "location": [1, 2, 3]}, ctx)

    assert created["object"] == "Cage"
    assert created["type"] == "LATTICE"
    assert created["lattice"]["points_u"] == 2
    assert created["location"] == [1.0, 2.0, 3.0]
    assert "object.add" in _op_names(bpy)
    assert bpy.undo_pushes == ["niua:lattice.create"]

    report = dispatch_on_main(reg, "lattice.report", {"object": "Cage"}, ctx)
    assert report["lattice"]["point_count"] == 8
    assert report["lattice"]["properties"]["points_u"]["value"] == 2
    assert report["lattice"]["points"][0]["co_deform"] == [0.0, 0.0, 0.0]

    points_u = dispatch_on_main(reg, "lattice.set", {"object": "Cage", "property": "points_u", "value": "3"}, ctx)
    assert points_u["value"] == 3
    assert bpy.objects.get("Cage").data.points_u == 3

    interpolation = dispatch_on_main(
        reg,
        "lattice.set",
        {"object": "Cage", "property": "interpolation_type_u", "value": '"KEY_LINEAR"'},
        ctx,
    )
    assert interpolation["value"] == "KEY_LINEAR"

    point = dispatch_on_main(reg, "lattice.point_set", {"object": "Cage", "index": 0, "co_deform": [0.2, 0.3, 0.4]}, ctx)
    assert point["point"]["co_deform"] == [0.2, 0.3, 0.4]
    assert bpy.objects.get("Cage").data.points[0].co_deform == [0.2, 0.3, 0.4]
    assert bpy.undo_pushes[-1] == "niua:lattice.point_set"


def test_non_lattice_object_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "lattice.report", {"object": "Cube"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_point_index_out_of_range_fails_without_extra_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cage"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "lattice.point_set", {"object": "Cage", "index": 99, "co_deform": [0, 0, 0]}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_convert_to_mesh_unsupported_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cage"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "lattice.convert_to_mesh", {"object": "Cage", "name": "CageMesh"}, ctx)

    assert exc.value.code == PRECONDITION
    assert "object.convert" in _op_names(bpy)
    assert bpy.undo_pushes == []
