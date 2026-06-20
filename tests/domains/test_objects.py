from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


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
        self.op_calls = []
        self.ops = self._make_ops(root, objects)

    def _create(self, name: str, obj_type: str = "MESH", location=None, collection=None):
        obj = FakeObject(name, obj_type)
        if location is not None:
            obj.location = [float(v) for v in location]
        self.data.objects.add(obj)
        (collection or self.context.scene.collection).objects.link(obj)
        self.context.object = obj
        self.context.view_layer.objects.active = obj
        return obj

    def _make_ops(self, root, objects):
        bpy = self

        class Mesh:
            def primitive_cube_add(self, **kwargs):
                bpy.op_calls.append(("mesh.primitive_cube_add", kwargs))
                bpy._create("Cube", location=kwargs.get("location"), collection=root)

            def primitive_uv_sphere_add(self, **kwargs):
                bpy.op_calls.append(("mesh.primitive_uv_sphere_add", kwargs))
                bpy._create("Sphere", location=kwargs.get("location"), collection=root)

            def primitive_plane_add(self, **kwargs):
                bpy.op_calls.append(("mesh.primitive_plane_add", kwargs))
                bpy._create("Plane", location=kwargs.get("location"), collection=root)

            def primitive_cylinder_add(self, **kwargs):
                bpy.op_calls.append(("mesh.primitive_cylinder_add", kwargs))
                bpy._create("Cylinder", location=kwargs.get("location"), collection=root)

            def primitive_cone_add(self, **kwargs):
                bpy.op_calls.append(("mesh.primitive_cone_add", kwargs))
                bpy._create("Cone", location=kwargs.get("location"), collection=root)

            def primitive_torus_add(self, **kwargs):
                bpy.op_calls.append(("mesh.primitive_torus_add", kwargs))
                bpy._create("Torus", location=kwargs.get("location"), collection=root)

            def primitive_monkey_add(self, **kwargs):
                bpy.op_calls.append(("mesh.primitive_monkey_add", kwargs))
                bpy._create("Suzanne", location=kwargs.get("location"), collection=root)

        class ObjectOps:
            def empty_add(self, **kwargs):
                bpy.op_calls.append(("object.empty_add", kwargs))
                bpy._create("Empty", obj_type="EMPTY", location=kwargs.get("location"), collection=root)

        class Ed:
            def undo_push(self, message="", **kwargs):
                bpy.op_calls.append(("ed.undo_push", {"message": message, **kwargs}))

        return types.SimpleNamespace(mesh=Mesh(), object=ObjectOps(), ed=Ed())


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


def test_router_contains_object_create_tool() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert "object.create" in names


def test_router_contains_object_lifecycle_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"object.duplicate", "object.delete", "object.rename"} <= names


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


def test_create_dispatches_supported_primitives(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    cube = dispatch_on_main(
        reg,
        "object.create",
        {
            "type": "CUBE",
            "name": "HeroCube",
            "location": [3, 2, 1],
            "rotation": [0.1, 0.2, 0.3],
            "scale": [2, 2, 2],
            "size": 4.0,
            "calc_uvs": False,
        },
        ctx,
    )
    torus = dispatch_on_main(
        reg,
        "object.create",
        {
            "type": "TORUS",
            "name": "HeroTorus",
            "major_radius": 2.0,
            "minor_radius": 0.4,
            "major_segments": 24,
            "minor_segments": 8,
        },
        ctx,
    )
    empty = dispatch_on_main(
        reg,
        "object.create",
        {
            "type": "EMPTY",
            "name": "HeroEmpty",
            "empty_display_type": "CUBE",
            "radius": 1.5,
        },
        ctx,
    )

    assert cube["name"] == "HeroCube"
    assert torus["name"] == "HeroTorus"
    assert empty["name"] == "HeroEmpty"
    assert bpy.data.objects.get("HeroCube") is not None
    assert bpy.data.objects.get("HeroTorus") is not None
    assert bpy.data.objects.get("HeroEmpty").type == "EMPTY"
    calls = {name: kwargs for name, kwargs in bpy.op_calls}
    assert calls["mesh.primitive_cube_add"] == {
        "size": 4.0,
        "calc_uvs": False,
        "location": [3.0, 2.0, 1.0],
        "rotation": [0.1, 0.2, 0.3],
        "scale": [2.0, 2.0, 2.0],
    }
    assert calls["mesh.primitive_torus_add"] == {
        "major_radius": 2.0,
        "minor_radius": 0.4,
        "major_segments": 24,
        "minor_segments": 8,
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
    }
    assert calls["object.empty_add"] == {
        "type": "CUBE",
        "radius": 1.5,
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }


def test_duplicate_copies_or_links_data_and_preserves_collection(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    source = bpy.data.objects.get("Cube")

    copied = dispatch_on_main(
        reg,
        "object.duplicate",
        {"object": "Cube", "name": "CubeCopy", "offset": [1, 1, 1]},
        ctx,
    )
    linked = dispatch_on_main(
        reg,
        "object.duplicate",
        {"object": "Cube", "name": "CubeLinked", "linked": True},
        ctx,
    )

    copy_obj = bpy.data.objects.get("CubeCopy")
    linked_obj = bpy.data.objects.get("CubeLinked")
    assert copied["name"] == "CubeCopy"
    assert copied["location"] == [2.0, 3.0, 4.0]
    assert copy_obj.data is not source.data
    assert source.data.copies == 1
    assert [collection.name for collection in copy_obj.users_collection] == ["Props"]
    assert linked["name"] == "CubeLinked"
    assert linked_obj.data is source.data


def test_delete_removes_multiple_objects_and_rejects_empty_list(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    bpy._create("DeleteA")
    bpy._create("DeleteB")

    out = dispatch_on_main(reg, "object.delete", {"objects": "DeleteA, DeleteB"}, ctx)

    assert out == {"deleted": ["DeleteA", "DeleteB"], "count": 2}
    assert bpy.data.objects.get("DeleteA") is None
    assert bpy.data.objects.get("DeleteB") is None
    assert bpy.data.objects.removed == [("DeleteA", True), ("DeleteB", True)]
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "object.delete", {"objects": " , "}, ctx)
    assert exc.value.code == INVALID_PARAMS


def test_rename_updates_object_lookup(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "object.rename", {"object": "Cube", "name": "RenamedCube"}, ctx)

    assert out["name"] == "RenamedCube"
    assert bpy.data.objects.get("Cube") is None
    assert bpy.data.objects.get("RenamedCube") is not None
