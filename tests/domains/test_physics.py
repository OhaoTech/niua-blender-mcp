"""Physics GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import NOT_FOUND, BridgeError


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


def _rna(*props: FakeRnaProp):
    return types.SimpleNamespace(properties=[FakeRnaProp("rna_type", "POINTER", is_readonly=True), *props])


class FakeRigidBody:
    def __init__(self) -> None:
        self.type = "ACTIVE"
        self.mass = 1.0
        self.enabled = True
        self.kinematic = False
        self.bl_rna = _rna(
            FakeRnaProp("type", "ENUM"),
            FakeRnaProp("mass", "FLOAT"),
            FakeRnaProp("enabled", "BOOLEAN"),
            FakeRnaProp("kinematic", "BOOLEAN"),
        )


class FakeRigidBodyConstraint:
    def __init__(self) -> None:
        self.type = "FIXED"
        self.enabled = True
        self.breaking_threshold = 10.0
        self.bl_rna = _rna(
            FakeRnaProp("type", "ENUM"),
            FakeRnaProp("enabled", "BOOLEAN"),
            FakeRnaProp("breaking_threshold", "FLOAT"),
        )


class FakeField:
    def __init__(self, type: str = "FORCE") -> None:
        self.type = type
        self.strength = 1.0
        self.flow = 1.0
        self.bl_rna = _rna(
            FakeRnaProp("type", "ENUM"),
            FakeRnaProp("strength", "FLOAT"),
            FakeRnaProp("flow", "FLOAT"),
        )


class FakeSettings:
    def __init__(self) -> None:
        self.quality = 5
        self.mass = 0.3
        self.bl_rna = _rna(FakeRnaProp("quality", "INT"), FakeRnaProp("mass", "FLOAT"))


class FakeModifier:
    def __init__(self, name: str, type: str) -> None:
        self.name = name
        self.type = type
        self.show_viewport = True
        self.show_render = True
        self.settings = FakeSettings()
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("type", "ENUM", is_readonly=True),
            FakeRnaProp("show_viewport", "BOOLEAN"),
            FakeRnaProp("show_render", "BOOLEAN"),
        )


class FakeModifiers(list):
    def new(self, name: str, type: str) -> FakeModifier:
        mod = FakeModifier(name, type)
        self.append(mod)
        return mod

    def get(self, name: str):
        return next((mod for mod in self if mod.name == name), None)

    def remove(self, mod: FakeModifier) -> None:
        super().remove(mod)


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.rigid_body = None
        self.rigid_body_constraint = None
        self.field = None
        self.modifiers = FakeModifiers()
        self._selected = False
        self.mode = "OBJECT"

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


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
            self._on_call(**kwargs)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active_obj = None
        self.op_calls: list = []
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

        log = self.op_calls

        def _rb_add(type="ACTIVE", **kwargs):
            bpy._active_obj.rigid_body = FakeRigidBody()
            bpy._active_obj.rigid_body.type = type

        def _rb_remove(**kwargs):
            bpy._active_obj.rigid_body = None

        def _rbc_add(type="FIXED", **kwargs):
            bpy._active_obj.rigid_body_constraint = FakeRigidBodyConstraint()
            bpy._active_obj.rigid_body_constraint.type = type

        def _rbc_remove(**kwargs):
            bpy._active_obj.rigid_body_constraint = None

        def _modifier_add(type, **kwargs):
            bpy._active_obj.modifiers.new(name=type, type=type)

        def _modifier_remove(modifier, **kwargs):
            mod = bpy._active_obj.modifiers.get(modifier)
            if mod is not None:
                bpy._active_obj.modifiers.remove(mod)

        def _forcefield_toggle(**kwargs):
            field = bpy._active_obj.field
            if field is None or field.type == "NONE":
                bpy._active_obj.field = FakeField("FORCE")
            else:
                field.type = "NONE"

        class _ObjectOps:
            modifier_add = _Op(log, "object.modifier_add", on_call=_modifier_add)
            modifier_remove = _Op(log, "object.modifier_remove", on_call=_modifier_remove)
            forcefield_toggle = _Op(log, "object.forcefield_toggle", on_call=_forcefield_toggle)

            @staticmethod
            def mode_set(mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _RigidBodyOps:
            object_add = _Op(log, "rigidbody.object_add", on_call=_rb_add)
            object_remove = _Op(log, "rigidbody.object_remove", on_call=_rb_remove)
            constraint_add = _Op(log, "rigidbody.constraint_add", on_call=_rbc_add)
            constraint_remove = _Op(log, "rigidbody.constraint_remove", on_call=_rbc_remove)

        class _EdOps:
            @staticmethod
            def undo_push(message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(object=_ObjectOps(), rigidbody=_RigidBodyOps(), ed=_EdOps())

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


def _op_names(bpy: FakeBpy) -> list[str]:
    return [name for name, _ in bpy.op_calls]


def test_router_contains_physics_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "physics.report",
        "physics.add",
        "physics.remove",
        "physics.set",
        "physics.field_report",
        "physics.field_set",
    } <= names


def test_add_report_set_and_remove_rigid_body(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    obj.mode = "EDIT"
    reg = build_default_registry()

    added = dispatch_on_main(reg, "physics.add", {"object": "Cube", "type": "RIGID_BODY"}, ctx)
    assert added["physics"]["type"] == "ACTIVE"
    assert "rigidbody.object_add" in _op_names(bpy)
    assert bpy.mode_calls == ["OBJECT", "EDIT"]
    assert bpy.undo_pushes == ["mcp:physics.add"]

    report = dispatch_on_main(reg, "physics.report", {"object": "Cube"}, ctx)
    assert report["physics"]["RIGID_BODY"]["properties"]["mass"]["value"] == 1.0

    changed = dispatch_on_main(
        reg,
        "physics.set",
        {"object": "Cube", "type": "RIGID_BODY", "property": "mass", "value": "2.5"},
        ctx,
    )
    assert obj.rigid_body.mass == 2.5
    assert changed["value"] == 2.5
    assert bpy.undo_pushes[-1] == "mcp:physics.set"

    removed = dispatch_on_main(reg, "physics.remove", {"object": "Cube", "type": "RIGID_BODY"}, ctx)
    assert removed["physics"] is None
    assert obj.rigid_body is None
    assert bpy.undo_pushes[-1] == "mcp:physics.remove"


def test_force_field_workflow_uses_field_report(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Wind"))
    reg = build_default_registry()

    added = dispatch_on_main(reg, "physics.add", {"object": "Wind", "type": "FIELD"}, ctx)
    assert added["physics"]["type"] == "FORCE"
    assert "object.forcefield_toggle" in _op_names(bpy)

    changed = dispatch_on_main(
        reg,
        "physics.field_set",
        {"object": "Wind", "property": "strength", "value": "3.0"},
        ctx,
    )
    assert obj.field.strength == 3.0
    assert changed["value"] == 3.0

    report = dispatch_on_main(reg, "physics.field_report", {"object": "Wind"}, ctx)
    assert report["enabled"] is True
    assert report["field"]["properties"]["strength"]["value"] == 3.0

    removed = dispatch_on_main(reg, "physics.remove", {"object": "Wind", "type": "FIELD"}, ctx)
    assert removed["enabled"] is False
    assert obj.field.type == "NONE"


def test_modifier_backed_physics_type_uses_modifier_stack(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("ClothMesh"))
    reg = build_default_registry()

    added = dispatch_on_main(reg, "physics.add", {"object": "ClothMesh", "type": "CLOTH"}, ctx)
    assert added["physics"]["name"] == "CLOTH"
    assert added["physics"]["type"] == "CLOTH"
    assert "object.modifier_add" in _op_names(bpy)

    changed = dispatch_on_main(
        reg,
        "physics.set",
        {"object": "ClothMesh", "type": "CLOTH", "property": "settings.quality", "value": "8"},
        ctx,
    )
    assert obj.modifiers.get("CLOTH").settings.quality == 8
    assert changed["value"] == 8

    removed = dispatch_on_main(reg, "physics.remove", {"object": "ClothMesh", "type": "CLOTH"}, ctx)
    assert removed["physics"] is None
    assert list(obj.modifiers) == []


def test_set_missing_physics_stack_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "physics.set",
            {"object": "Cube", "type": "RIGID_BODY", "property": "mass", "value": "2"},
            ctx,
        )

    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []


def test_remove_missing_physics_stack_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "physics.remove", {"object": "Cube", "type": "RIGID_BODY"}, ctx)

    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []
