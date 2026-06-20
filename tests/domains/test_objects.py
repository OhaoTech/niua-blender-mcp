from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class _NamedList(list):
    def get(self, name: str):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None

    def keys(self):
        return [item.name for item in self]


class _ObjectLinks(_NamedList):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def link(self, obj):
        if obj not in self:
            self.append(obj)
        if self.owner not in obj.users_collection:
            obj.users_collection.append(self.owner)

    def unlink(self, obj):
        if obj in self:
            self.remove(obj)
        if self.owner in obj.users_collection:
            obj.users_collection.remove(self.owner)


class FakeMatrix:
    def __init__(self, tx=0.0, ty=0.0, tz=0.0) -> None:
        self.tx = float(tx)
        self.ty = float(ty)
        self.tz = float(tz)

    def __iter__(self):
        yield [1.0, 0.0, 0.0, self.tx]
        yield [0.0, 1.0, 0.0, self.ty]
        yield [0.0, 0.0, 1.0, self.tz]
        yield [0.0, 0.0, 0.0, 1.0]

    def __matmul__(self, value):
        x, y, z = value
        return [float(x) + self.tx, float(y) + self.ty, float(z) + self.tz]


class FakeDataBlock:
    def __init__(self, name: str) -> None:
        self.name = name
        self.copies = 0

    def copy(self):
        self.copies += 1
        return FakeDataBlock(f"{self.name}.copy")


class FakeObject:
    def __init__(self, name: str, obj_type: str = "MESH", data=None) -> None:
        self.name = name
        self.type = obj_type
        self.data = data or FakeDataBlock(f"{name}Data")
        self.location = [1.0, 2.0, 3.0]
        self.rotation_euler = [0.1, 0.2, 0.3]
        self.scale = [2.0, 2.0, 2.0]
        self.delta_location = [0.0, 0.0, 0.0]
        self.delta_rotation_euler = [0.0, 0.0, 0.0]
        self.delta_scale = [1.0, 1.0, 1.0]
        self.rotation_mode = "XYZ"
        self.dimensions = [4.0, 5.0, 6.0]
        self.parent = None
        self.users_collection = []
        self.matrix_world = FakeMatrix(1.0, 2.0, 3.0)
        self.bound_box = [
            (-1.0, -1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, 1.0, 1.0),
            (1.0, -1.0, -1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, -1.0),
            (1.0, 1.0, 1.0),
        ]

    def copy(self):
        dup = FakeObject(f"{self.name}.copy", self.type, self.data)
        dup.location = list(self.location)
        dup.rotation_euler = list(self.rotation_euler)
        dup.scale = list(self.scale)
        dup.delta_location = list(self.delta_location)
        dup.delta_rotation_euler = list(self.delta_rotation_euler)
        dup.delta_scale = list(self.delta_scale)
        dup.rotation_mode = self.rotation_mode
        dup.dimensions = list(self.dimensions)
        dup.matrix_world = self.matrix_world
        dup.bound_box = list(self.bound_box)
        return dup


class FakeCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.objects = _ObjectLinks(self)


class FakeObjects(_NamedList):
    def __init__(self) -> None:
        super().__init__()
        self.removed = []

    def add(self, obj):
        base = obj.name
        name = base
        index = 1
        while self.get(name) is not None:
            name = f"{base}.{index:03d}"
            index += 1
        obj.name = name
        self.append(obj)
        return obj

    def remove(self, obj, do_unlink=False):
        self.removed.append((obj.name, do_unlink))
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        if obj in self:
            list.remove(self, obj)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        root = FakeCollection("Scene Collection")
        props = FakeCollection("Props")
        cube = FakeObject("Cube")
        props.objects.link(cube)
        objects = FakeObjects()
        objects.add(cube)
        self.data = types.SimpleNamespace(objects=objects, materials={})
        self.context = types.SimpleNamespace(
            scene=types.SimpleNamespace(name="Scene", objects=objects, collection=root),
            object=cube,
            view_layer=types.SimpleNamespace(objects=types.SimpleNamespace(active=cube)),
        )
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None))


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_object_read_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "object.transform_get",
        "object.bounds",
    } <= names


def test_transform_get_returns_object_state(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "object.transform_get", {"object": "Cube"}, ctx)

    assert out["name"] == "Cube"
    assert out["type"] == "MESH"
    assert out["location"] == [1.0, 2.0, 3.0]
    assert out["rotation"] == [0.1, 0.2, 0.3]
    assert out["scale"] == [2.0, 2.0, 2.0]
    assert out["rotation_mode"] == "XYZ"
    assert out["dimensions"] == [4.0, 5.0, 6.0]
    assert out["collections"] == ["Props"]
    assert out["matrix_world"][0] == [1.0, 0.0, 0.0, 1.0]


def test_bounds_returns_local_and_world_corners(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "object.bounds", {"object": "Cube"}, ctx)

    assert out["object"] == "Cube"
    assert out["dimensions"] == [4.0, 5.0, 6.0]
    assert out["local"][0] == [-1.0, -1.0, -1.0]
    assert out["world"][0] == [0.0, 1.0, 2.0]
    assert out["center"] == [1.0, 2.0, 3.0]
