"""Point cloud GUI-parity domain tests (fake-bpy)."""

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


class FakeRnaProp:
    def __init__(self, identifier: str, type: str, *, is_readonly: bool = False) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = False
        self.array_length = 0
        self.enum_items = []
        self.enum_items_static = []


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


class FakePoint:
    def __init__(self, index: int, co: list[float], radius: float) -> None:
        self.index = index
        self.co = co
        self.radius = radius


class FakeAttributeValue:
    def __init__(self, value) -> None:
        self.value = value


class FakeVectorAttributeValue:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector


class FakeAttribute:
    def __init__(self, name: str, data_type: str, domain: str, data: list) -> None:
        self.name = name
        self.data_type = data_type
        self.domain = domain
        self.data = data


class FakePointCloudData:
    def __init__(self, name: str = "CloudData") -> None:
        self.name = name
        self.id_type = "POINTCLOUD"
        self.use_fake_user = False
        self.use_extra_user = False
        self.is_runtime_data = False
        self.tag = False
        self.users = 1
        self.points = [
            FakePoint(0, [0.0, 0.0, 0.0], 0.1),
            FakePoint(1, [1.0, 0.0, 0.0], 0.2),
        ]
        self.materials = []
        self.attributes = [
            FakeAttribute(
                "position",
                "FLOAT_VECTOR",
                "POINT",
                [FakeVectorAttributeValue([0.0, 0.0, 0.0]), FakeVectorAttributeValue([1.0, 0.0, 0.0])],
            ),
            FakeAttribute("radius", "FLOAT", "POINT", [FakeAttributeValue(0.1), FakeAttributeValue(0.2)]),
        ]
        self.color_attributes = []
        self.animation_data = None
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("id_type", "ENUM", is_readonly=True),
            FakeRnaProp("users", "INT", is_readonly=True),
            FakeRnaProp("use_fake_user", "BOOLEAN"),
            FakeRnaProp("use_extra_user", "BOOLEAN"),
            FakeRnaProp("is_runtime_data", "BOOLEAN"),
            FakeRnaProp("tag", "BOOLEAN"),
            FakeRnaProp("points", "COLLECTION", is_readonly=True),
            FakeRnaProp("materials", "COLLECTION", is_readonly=True),
            FakeRnaProp("attributes", "COLLECTION", is_readonly=True),
            FakeRnaProp("color_attributes", "COLLECTION", is_readonly=True),
            FakeRnaProp("animation_data", "POINTER", is_readonly=True),
        )


class FakeObj:
    def __init__(self, name: str, type: str = "POINTCLOUD", data: FakePointCloudData | None = None) -> None:
        self.name = name
        self.type = type
        self.data = data or FakePointCloudData(f"{name}Data")
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


class FakePointClouds(list):
    def get(self, name: str):
        return next((pointcloud for pointcloud in self if pointcloud.name == name), None)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = FakeObjects()
        self.pointclouds = FakePointClouds()
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

        class _ObjectOps:
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
        if getattr(obj, "data", None) is not None and obj.data not in self.pointclouds:
            self.pointclouds.append(obj.data)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        return types.SimpleNamespace(objects=self.objects, pointclouds=self.pointclouds)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_pointcloud_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "pointcloud.list",
        "pointcloud.report",
        "pointcloud.set",
        "pointcloud.attributes",
    } <= names


def test_list_report_and_attributes_by_object_name(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cloud", data=FakePointCloudData("CloudData")))
    reg = build_default_registry()

    listed = dispatch_on_main(reg, "pointcloud.list", {}, ctx)
    assert listed["pointcloud_count"] == 1
    assert listed["pointclouds"][0]["object"] == "Cloud"
    assert listed["pointclouds"][0]["point_count"] == 2

    report = dispatch_on_main(reg, "pointcloud.report", {"name_or_object": "Cloud"}, ctx)
    assert report["object"] == "Cloud"
    assert report["pointcloud"]["data"] == "CloudData"
    assert report["pointcloud"]["point_count"] == 2
    assert report["pointcloud"]["properties"]["use_fake_user"]["value"] is False

    attrs = dispatch_on_main(reg, "pointcloud.attributes", {"name_or_object": "Cloud"}, ctx)
    assert attrs["object"] == "Cloud"
    assert attrs["pointcloud"] == "CloudData"
    assert attrs["attribute_count"] == 2
    assert attrs["attributes"][0]["name"] == "position"
    assert attrs["attributes"][0]["sample"] == [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert attrs["attributes"][1]["sample"] == [0.1, 0.2]


def test_report_can_resolve_by_data_block_name(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cloud", data=FakePointCloudData("CloudData")))
    reg = build_default_registry()

    report = dispatch_on_main(reg, "pointcloud.report", {"name_or_object": "CloudData"}, ctx)

    assert report["object"] == "Cloud"
    assert report["pointcloud"]["data"] == "CloudData"


def test_set_pointcloud_data_property_pushes_undo(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cloud", data=FakePointCloudData("CloudData")))
    reg = build_default_registry()

    changed = dispatch_on_main(reg, "pointcloud.set", {"name_or_object": "Cloud", "property": "use_fake_user", "value": "true"}, ctx)

    assert changed["object"] == "Cloud"
    assert changed["property"] == "use_fake_user"
    assert changed["value"] is True
    assert obj.data.use_fake_user is True
    assert bpy.undo_pushes == ["mcp:pointcloud.set"]


def test_non_pointcloud_object_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH", data=None))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "pointcloud.report", {"name_or_object": "Cube"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []

def test_read_only_property_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cloud", data=FakePointCloudData("CloudData")))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "pointcloud.set", {"name_or_object": "Cloud", "property": "points", "value": "[]"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []
