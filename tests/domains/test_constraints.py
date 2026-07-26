"""Constraints GUI-parity domain tests (fake-bpy)."""

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
    def __init__(
        self,
        identifier: str,
        type: str,
        *,
        is_readonly: bool = False,
        is_array: bool = False,
        array_length: int = 0,
    ) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = is_array
        self.array_length = array_length
        self.enum_items = []


class FakeConstraint:
    def __init__(self, name: str, type: str = "COPY_LOCATION") -> None:
        self.name = name
        self.type = type
        self.influence = 1.0
        self.mute = False
        self.target = None
        self.subtarget = ""
        self.bl_rna = types.SimpleNamespace(
            properties=[
                FakeRnaProp("rna_type", "POINTER", is_readonly=True),
                FakeRnaProp("name", "STRING"),
                FakeRnaProp("type", "ENUM", is_readonly=True),
                FakeRnaProp("influence", "FLOAT"),
                FakeRnaProp("mute", "BOOLEAN"),
                FakeRnaProp("target", "POINTER"),
                FakeRnaProp("subtarget", "STRING"),
            ]
        )


class FakeConstraints(list):
    def get(self, name: str):
        return next((constraint for constraint in self if constraint.name == name), None)

    def new(self, type: str):
        if type == "NOPE":
            raise TypeError("unsupported constraint")
        constraint = FakeConstraint(type, type)
        self.append(constraint)
        return constraint

    def remove(self, constraint) -> None:
        super().remove(constraint)


class FakePoseBone:
    def __init__(self, name: str) -> None:
        self.name = name
        self.constraints = FakeConstraints()


class FakePoseBones:
    def __init__(self) -> None:
        self._bones: dict[str, FakePoseBone] = {}

    def add(self, name: str) -> FakePoseBone:
        bone = FakePoseBone(name)
        self._bones[name] = bone
        return bone

    def get(self, name: str):
        return self._bones.get(name)

    def __iter__(self):
        return iter(self._bones.values())


class FakePose:
    def __init__(self) -> None:
        self.bones = FakePoseBones()


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.constraints = FakeConstraints()
        self.pose = FakePose() if type == "ARMATURE" else None
        self._selected = False
        self.mode = "OBJECT"

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active_obj = None
        self.mode_calls: list[str] = []
        self.undo_pushes: list[str] = []

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

            @property
            def object(self_inner):
                return bpy._active_obj

            window_manager = types.SimpleNamespace(windows=[])

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
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        store = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))
            materials: dict = {}

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_constraints_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "constraints.list",
        "constraints.add",
        "constraints.remove",
        "constraints.report",
        "constraints.set",
    } <= names


def test_add_object_constraint_uses_object_mode_and_pushes_undo(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    obj.mode = "EDIT"
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "constraints.add",
        {"object": "Cube", "type": "COPY_LOCATION", "name": "CopyLoc"},
        ctx,
    )

    assert result["object"] == "Cube"
    assert result["owner"] == "OBJECT"
    assert result["bone"] is None
    assert result["constraint"]["name"] == "CopyLoc"
    assert result["constraint"]["type"] == "COPY_LOCATION"
    assert [constraint.name for constraint in obj.constraints] == ["CopyLoc"]
    assert bpy.mode_calls == ["OBJECT", "EDIT"]
    assert bpy.undo_pushes == ["mcp:constraints.add"]


def test_list_object_constraints_is_read_only(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    constraint = obj.constraints.new(type="COPY_LOCATION")
    constraint.name = "CopyLoc"
    constraint.influence = 0.5
    reg = build_default_registry()

    result = dispatch_on_main(reg, "constraints.list", {"object": "Cube"}, ctx)

    assert result["constraint_count"] == 1
    assert result["constraints"] == [
        {
            "index": 0,
            "name": "CopyLoc",
            "type": "COPY_LOCATION",
            "influence": 0.5,
            "mute": False,
            "target": None,
            "subtarget": "",
        }
    ]
    assert bpy.undo_pushes == []


def test_report_named_constraint_uses_live_rna_properties(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    constraint = obj.constraints.new(type="COPY_LOCATION")
    constraint.name = "CopyLoc"
    constraint.influence = 0.35
    constraint.mute = True
    reg = build_default_registry()

    result = dispatch_on_main(reg, "constraints.report", {"object": "Cube", "name": "CopyLoc"}, ctx)

    report = result["constraint"]
    assert report["name"] == "CopyLoc"
    assert report["properties"]["influence"]["type"] == "FLOAT"
    assert report["properties"]["influence"]["value"] == 0.35
    assert report["properties"]["mute"]["value"] is True
    assert "rna_type" not in report["properties"]
    assert bpy.undo_pushes == []


def test_set_constraint_property_from_json_value(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    constraint = obj.constraints.new(type="COPY_LOCATION")
    constraint.name = "CopyLoc"
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "constraints.set",
        {"object": "Cube", "name": "CopyLoc", "property": "influence", "value": "0.25"},
        ctx,
    )

    assert constraint.influence == 0.25
    assert result["property"] == "influence"
    assert result["value"] == 0.25
    assert result["constraint"]["properties"]["influence"]["value"] == 0.25
    assert bpy.undo_pushes == ["mcp:constraints.set"]


def test_set_constraint_object_pointer_from_json_ref(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    constraint = obj.constraints.new(type="COPY_LOCATION")
    constraint.name = "CopyLoc"
    target = bpy.add(FakeObj("Target"))
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "constraints.set",
        {"object": "Cube", "name": "CopyLoc", "property": "target", "value": '{"object":"Target"}'},
        ctx,
    )

    assert constraint.target is target
    assert result["value"] == {"name": "Target", "type": "MESH"}
    assert result["constraint"]["properties"]["target"]["value"] == {"name": "Target", "type": "MESH"}
    assert bpy.undo_pushes == ["mcp:constraints.set"]


def test_remove_object_constraint_pushes_undo(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    constraint = obj.constraints.new(type="COPY_LOCATION")
    constraint.name = "CopyLoc"
    reg = build_default_registry()

    result = dispatch_on_main(reg, "constraints.remove", {"object": "Cube", "name": "CopyLoc"}, ctx)

    assert result["constraint_count"] == 0
    assert list(obj.constraints) == []
    assert bpy.undo_pushes == ["mcp:constraints.remove"]


def test_add_pose_bone_constraint_uses_pose_owner(env) -> None:
    ctx, bpy = env
    armature = bpy.add(FakeObj("Rig", type="ARMATURE"))
    armature.pose.bones.add("Spine")
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "constraints.add",
        {"object": "Rig", "owner": "BONE", "bone": "Spine", "type": "IK", "name": "ArmIK"},
        ctx,
    )

    assert result["object"] == "Rig"
    assert result["owner"] == "BONE"
    assert result["bone"] == "Spine"
    assert result["constraint"]["name"] == "ArmIK"
    assert [constraint.name for constraint in armature.pose.bones.get("Spine").constraints] == ["ArmIK"]
    assert bpy.mode_calls == ["POSE", "OBJECT"]
    assert bpy.undo_pushes == ["mcp:constraints.add"]


def test_bone_owner_requires_bone_name(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Rig", type="ARMATURE"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "constraints.list", {"object": "Rig", "owner": "BONE"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []
