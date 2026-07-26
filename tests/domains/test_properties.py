from __future__ import annotations

import json
import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import NOT_FOUND, PRECONDITION, BridgeError


class FakeEnumItem:
    def __init__(self, identifier: str, name: str = "") -> None:
        self.identifier = identifier
        self.name = name or identifier.title()


class FakeProp:
    def __init__(
        self,
        identifier: str,
        type: str = "STRING",
        *,
        is_readonly: bool = False,
        is_array: bool = False,
        array_length: int = 0,
        enum_items: list[FakeEnumItem] | None = None,
    ) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = f"{identifier} property"
        self.type = type
        self.subtype = "NONE"
        self.is_readonly = is_readonly
        self.is_array = is_array
        self.array_length = array_length
        self.enum_items = enum_items or []


class FakeRna:
    def __init__(self, props: list[FakeProp]) -> None:
        self.properties = props


class FakeID:
    bl_rna = FakeRna([FakeProp("rna_type", "POINTER")])

    def __init__(self) -> None:
        self._idprops: dict[str, object] = {}

    def keys(self):
        return list(self._idprops)

    def __getitem__(self, key: str):
        return self._idprops[key]

    def __setitem__(self, key: str, value) -> None:
        self._idprops[key] = value

    def __delitem__(self, key: str) -> None:
        del self._idprops[key]


class FakeModifier:
    bl_rna = FakeRna(
        [
            FakeProp("rna_type", "POINTER"),
            FakeProp("name"),
            FakeProp("type", "ENUM", is_readonly=True, enum_items=[FakeEnumItem("BEVEL")]),
            FakeProp("width", "FLOAT"),
        ]
    )

    def __init__(self, name: str) -> None:
        self.name = name
        self.type = "BEVEL"
        self.width = 0.1


class FakeCollection(list):
    def get(self, name: str):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class FakeMesh(FakeID):
    bl_rna = FakeRna(
        [
            FakeProp("rna_type", "POINTER"),
            FakeProp("name"),
            FakeProp("vertices", "COLLECTION", is_readonly=True),
            FakeProp("use_auto_smooth", "BOOLEAN"),
        ]
    )

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.vertices = [object(), object()]
        self.use_auto_smooth = False


class FakeObject(FakeID):
    bl_rna = FakeRna(
        [
            FakeProp("rna_type", "POINTER"),
            FakeProp("name"),
            FakeProp("type", "ENUM", is_readonly=True, enum_items=[FakeEnumItem("MESH")]),
            FakeProp("location", "FLOAT", is_array=True, array_length=3),
            FakeProp("hide_viewport", "BOOLEAN"),
            FakeProp("data", "POINTER", is_readonly=True),
            FakeProp("modifiers", "COLLECTION", is_readonly=True),
        ]
    )

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.type = "MESH"
        self.location = [0.0, 0.0, 0.0]
        self.hide_viewport = False
        self.data = FakeMesh(f"{name}Mesh")
        self.modifiers = FakeCollection([FakeModifier("Bevel")])


class FakeObjects(FakeCollection):
    pass


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = FakeObjects()
        self.meshes = FakeCollection()
        self.undo_pushes: list[str] = []
        self.context = types.SimpleNamespace()

        class _EdOps:
            def __init__(self, outer) -> None:
                self.outer = outer

            def undo_push(self, message: str = "", **_kwargs):
                self.outer.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(ed=_EdOps(self))

    @property
    def data(self):
        return types.SimpleNamespace(objects=self.objects, meshes=self.meshes)

    def add(self, obj: FakeObject) -> FakeObject:
        self.objects.append(obj)
        self.meshes.append(obj.data)
        return obj


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_properties_tools_are_exposed() -> None:
    names = {spec.name for spec in build_router().specs()}

    assert {
        "properties.report",
        "properties.object_report",
        "properties.get",
        "properties.set",
        "properties.unset",
    } <= names


def test_object_report_includes_object_data_modifiers_and_custom_properties(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObject("Cube/001"))
    obj["artist_note"] = "hero"
    obj.data["mesh_note"] = {"lod": 0}
    reg = build_default_registry()

    result = dispatch_on_main(reg, "properties.object_report", {"object": "Cube/001"}, ctx)

    object_props = {prop["identifier"]: prop for prop in result["object_properties"]}
    data_props = {prop["identifier"]: prop for prop in result["data"]["properties"]}
    modifier_props = {prop["identifier"]: prop for prop in result["modifiers"][0]["properties"]}
    assert set(object_props) == {"name", "type", "location", "hide_viewport", "data", "modifiers"}
    assert set(data_props) == {"name", "vertices", "use_auto_smooth"}
    assert set(modifier_props) == {"name", "type", "width"}
    assert object_props["location"]["path"] == "object:Cube%2F001/location"
    assert data_props["use_auto_smooth"]["path"] == "object:Cube%2F001/data/use_auto_smooth"
    assert result["custom_properties"] == [
        {"key": "artist_note", "path": "object:Cube%2F001/idprops/artist_note", "value": "hero"}
    ]
    assert result["data"]["custom_properties"] == [
        {"key": "mesh_note", "path": "object:Cube%2F001/data/idprops/mesh_note", "value": {"lod": 0}}
    ]
    assert result["coverage"]["missing_object_properties"] == []
    assert result["coverage"]["missing_data_properties"] == []


def test_get_and_set_support_stable_object_paths_with_dotted_names(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObject("Cube.001"))
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "properties.set",
        {"path": "object:Cube.001/location", "value": json.dumps([1, 2, 3])},
        ctx,
    )

    assert obj.location == [1, 2, 3]
    assert out == {"path": "object:Cube.001/location", "value": [1, 2, 3]}
    assert dispatch_on_main(reg, "properties.get", {"path": "object:Cube.001/location"}, ctx)["value"] == [
        1,
        2,
        3,
    ]
    assert bpy.undo_pushes == ["mcp:properties.set"]


def test_generic_report_get_and_set_support_data_collection_paths(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObject("Cube"))
    obj.data.name = "Mesh.001"
    reg = build_default_registry()

    report = dispatch_on_main(reg, "properties.report", {"path": "data:meshes/Mesh.001"}, ctx)
    props = {prop["identifier"]: prop for prop in report["properties"]}
    assert set(props) == {"name", "vertices", "use_auto_smooth"}
    assert props["use_auto_smooth"]["path"] == "data:meshes/Mesh.001/use_auto_smooth"

    written = dispatch_on_main(
        reg,
        "properties.set",
        {"path": "data:meshes/Mesh.001/use_auto_smooth", "value": "true"},
        ctx,
    )

    assert obj.data.use_auto_smooth is True
    assert written == {"path": "data:meshes/Mesh.001/use_auto_smooth", "value": True}
    assert dispatch_on_main(
        reg,
        "properties.get",
        {"path": "data:meshes/Mesh.001/use_auto_smooth"},
        ctx,
    )["value"] is True


def test_custom_properties_round_trip_and_unset(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObject("Cube"))
    reg = build_default_registry()

    dispatch_on_main(
        reg,
        "properties.set",
        {"path": "object:Cube/idprops/notes", "value": json.dumps({"role": "hero"})},
        ctx,
    )
    assert obj["notes"] == {"role": "hero"}
    assert dispatch_on_main(reg, "properties.get", {"path": "object:Cube/idprops/notes"}, ctx)["value"] == {
        "role": "hero"
    }

    result = dispatch_on_main(reg, "properties.unset", {"path": "object:Cube/idprops/notes"}, ctx)

    assert result == {"path": "object:Cube/idprops/notes", "removed": True}
    assert "notes" not in obj.keys()
    assert bpy.undo_pushes == ["mcp:properties.set", "mcp:properties.unset"]


def test_get_missing_path_raises_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObject("Cube"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "properties.get", {"path": "object:Cube/missing"}, ctx)

    assert exc.value.code == NOT_FOUND


def test_set_readonly_property_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObject("Cube"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "properties.set", {"path": "object:Cube/type", "value": json.dumps("EMPTY")}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []
