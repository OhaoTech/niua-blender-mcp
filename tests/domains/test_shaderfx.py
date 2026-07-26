"""Shader effects GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import NOT_FOUND, PRECONDITION, BridgeError


class FakeEnumItem:
    def __init__(self, identifier: str, name: str) -> None:
        self.identifier = identifier
        self.name = name


class FakeRnaProp:
    def __init__(
        self,
        identifier: str,
        type: str,
        *,
        is_readonly: bool = False,
        is_array: bool = False,
        enum_items: list[FakeEnumItem] | None = None,
    ) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = is_array
        self.array_length = 2 if is_array else 0
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


SHADERFX_TYPES = [
    FakeEnumItem("FX_BLUR", "Blur"),
    FakeEnumItem("FX_COLORIZE", "Colorize"),
    FakeEnumItem("FX_WAVE", "Wave Distortion"),
]


class FakeShaderFx:
    def __init__(self, name: str, type: str) -> None:
        self.name = name
        self.type = type
        self.show_viewport = True
        self.show_render = True
        self.show_in_editmode = False
        self.show_expanded = True
        self.size = [50.0, 50.0]
        self.samples = 8
        self.rotation = 0.0
        self.use_dof_mode = False
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("type", "ENUM", is_readonly=True, enum_items=SHADERFX_TYPES),
            FakeRnaProp("show_viewport", "BOOLEAN"),
            FakeRnaProp("show_render", "BOOLEAN"),
            FakeRnaProp("show_in_editmode", "BOOLEAN"),
            FakeRnaProp("show_expanded", "BOOLEAN"),
            FakeRnaProp("size", "FLOAT", is_array=True),
            FakeRnaProp("samples", "INT"),
            FakeRnaProp("rotation", "FLOAT"),
            FakeRnaProp("use_dof_mode", "BOOLEAN"),
        )


class FakeShaderEffects(list):
    def new(self, name: str, type: str):
        effect = FakeShaderFx(name=name, type=type)
        self.append(effect)
        return effect

    def get(self, name: str):
        return next((effect for effect in self if effect.name == name), None)

    def find(self, name: str) -> int:
        for index, effect in enumerate(self):
            if effect.name == name:
                return index
        return -1

    def remove(self, effect) -> None:
        super().remove(effect)


class FakeObj:
    def __init__(self, name: str, type: str = "GREASEPENCIL", *, supports_shaderfx: bool = True) -> None:
        self.name = name
        self.type = type
        if supports_shaderfx:
            self.shader_effects = FakeShaderEffects()
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
            return self._on_call(**kwargs)
        return None


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

        def _shaderfx_add(type: str = "FX_BLUR", **kwargs):
            bpy._active_obj.shader_effects.new(name=type, type=type)

        def _shaderfx_remove(shaderfx: str = "", **kwargs):
            effect = bpy._active_obj.shader_effects.get(shaderfx)
            if effect is not None:
                bpy._active_obj.shader_effects.remove(effect)

        class _ObjectOps:
            shaderfx_add = _Op(log, "object.shaderfx_add", on_call=_shaderfx_add)
            shaderfx_remove = _Op(log, "object.shaderfx_remove", on_call=_shaderfx_remove)

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
        self.types = types.SimpleNamespace(ShaderFx=types.SimpleNamespace(bl_rna=_rna(FakeRnaProp("type", "ENUM", enum_items=SHADERFX_TYPES))))

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


def test_router_contains_shaderfx_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "shaderfx.list",
        "shaderfx.types",
        "shaderfx.add",
        "shaderfx.remove",
        "shaderfx.report",
        "shaderfx.set",
    } <= names


def test_types_reports_runtime_shaderfx_enum(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    result = dispatch_on_main(reg, "shaderfx.types", {}, ctx)

    assert result["type_count"] == 3
    assert result["types"][0] == {"identifier": "FX_BLUR", "name": "Blur"}


def test_add_list_report_set_and_remove_shaderfx(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Sketch"))
    obj.mode = "EDIT"
    reg = build_default_registry()

    added = dispatch_on_main(reg, "shaderfx.add", {"object": "Sketch", "type": "FX_BLUR", "name": "LensBlur"}, ctx)

    assert added["object"] == "Sketch"
    assert added["shaderfx"]["name"] == "LensBlur"
    assert added["shaderfx"]["type"] == "FX_BLUR"
    assert "object.shaderfx_add" in _op_names(bpy)
    assert bpy.mode_calls == ["OBJECT", "EDIT"]
    assert bpy.undo_pushes == ["mcp:shaderfx.add"]

    listed = dispatch_on_main(reg, "shaderfx.list", {"object": "Sketch"}, ctx)
    assert listed["shaderfx_count"] == 1
    assert listed["shaderfx"][0]["name"] == "LensBlur"

    samples = dispatch_on_main(
        reg,
        "shaderfx.set",
        {"object": "Sketch", "name": "LensBlur", "property": "samples", "value": "12"},
        ctx,
    )
    assert samples["value"] == 12
    assert obj.shader_effects[0].samples == 12

    visible = dispatch_on_main(
        reg,
        "shaderfx.set",
        {"object": "Sketch", "name": "LensBlur", "property": "show_viewport", "value": "false"},
        ctx,
    )
    assert visible["value"] is False

    report = dispatch_on_main(reg, "shaderfx.report", {"object": "Sketch", "name": "LensBlur"}, ctx)
    assert report["shaderfx"]["properties"]["samples"]["value"] == 12
    assert report["shaderfx"]["properties"]["show_viewport"]["value"] is False
    assert "rna_type" not in report["shaderfx"]["properties"]

    removed = dispatch_on_main(reg, "shaderfx.remove", {"object": "Sketch", "name": "LensBlur"}, ctx)
    assert removed["shaderfx_count"] == 0
    assert "object.shaderfx_remove" in _op_names(bpy)
    assert bpy.undo_pushes[-1] == "mcp:shaderfx.remove"


def test_missing_shaderfx_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Sketch"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "shaderfx.set",
            {"object": "Sketch", "name": "Missing", "property": "samples", "value": "4"},
            ctx,
        )

    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []


def test_object_without_shader_effect_stack_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH", supports_shaderfx=False))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "shaderfx.add", {"object": "Cube", "type": "FX_BLUR"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []
