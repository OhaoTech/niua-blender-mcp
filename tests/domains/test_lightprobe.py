"""Light probe GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, PRECONDITION, BridgeError


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
        enum_items: list[FakeEnumItem] | None = None,
    ) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = False
        self.array_length = 0
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


PROBE_TYPES = [FakeEnumItem("SPHERE"), FakeEnumItem("PLANE"), FakeEnumItem("VOLUME")]


class FakeLightProbeData:
    def __init__(self, type: str = "SPHERE", name: str = "LightProbe") -> None:
        self.name = name
        self.type = type
        self.clip_start = 0.8
        self.show_clip = False
        self.show_influence = True
        self.influence_distance = 2.5 if type == "SPHERE" else 0.3
        self.visibility_buffer_bias = 0.1
        self.visibility_bleed_bias = 0.0
        self.visibility_blur = 0.2
        self.visibility_collection = None
        self.invert_visibility_collection = False
        self.show_data = False
        self.use_data_display = False
        self.data_display_size = 1.0
        self.falloff = 0.2
        self.clip_end = 20.0
        self.intensity = 1.0
        self.resolution_x = 4
        self.resolution_y = 4
        self.resolution_z = 4
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("type", "ENUM", is_readonly=True, enum_items=PROBE_TYPES),
            FakeRnaProp("clip_start", "FLOAT"),
            FakeRnaProp("show_clip", "BOOLEAN"),
            FakeRnaProp("show_influence", "BOOLEAN"),
            FakeRnaProp("influence_distance", "FLOAT"),
            FakeRnaProp("visibility_buffer_bias", "FLOAT"),
            FakeRnaProp("visibility_bleed_bias", "FLOAT"),
            FakeRnaProp("visibility_blur", "FLOAT"),
            FakeRnaProp("visibility_collection", "POINTER"),
            FakeRnaProp("invert_visibility_collection", "BOOLEAN"),
            FakeRnaProp("show_data", "BOOLEAN"),
            FakeRnaProp("use_data_display", "BOOLEAN"),
            FakeRnaProp("data_display_size", "FLOAT"),
            FakeRnaProp("falloff", "FLOAT"),
            FakeRnaProp("clip_end", "FLOAT"),
            FakeRnaProp("intensity", "FLOAT"),
            FakeRnaProp("resolution_x", "INT"),
            FakeRnaProp("resolution_y", "INT"),
            FakeRnaProp("resolution_z", "INT"),
        )


class FakeObj:
    def __init__(self, name: str, type: str = "LIGHT_PROBE", probe_type: str = "SPHERE") -> None:
        self.name = name
        self.type = type
        self.data = FakeLightProbeData(probe_type, name)
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
        self.collections = {}
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

        def _lightprobe_add(type: str = "SPHERE", location=None, **kwargs):
            obj = FakeObj(type.title(), probe_type=type)
            obj.location = list(location or [0.0, 0.0, 0.0])
            self.add(obj)
            return {"FINISHED"}

        class _ObjectOps:
            lightprobe_add = _Op(log, "object.lightprobe_add", on_call=_lightprobe_add)

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
        return types.SimpleNamespace(objects=self.objects, collections=self.collections, materials={})


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _op_names(bpy: FakeBpy) -> list[str]:
    return [name for name, _ in bpy.op_calls]


def test_router_contains_lightprobe_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "lightprobe.create",
        "lightprobe.list",
        "lightprobe.report",
        "lightprobe.set",
    } <= names


def test_create_list_report_and_set_light_probe(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(reg, "lightprobe.create", {"type": "SPHERE", "name": "Probe", "location": [1, 2, 3]}, ctx)

    assert created["object"] == "Probe"
    assert created["type"] == "LIGHT_PROBE"
    assert created["lightprobe"]["type"] == "SPHERE"
    assert created["location"] == [1.0, 2.0, 3.0]
    assert "object.lightprobe_add" in _op_names(bpy)
    assert bpy.undo_pushes == ["niua:lightprobe.create"]

    listed = dispatch_on_main(reg, "lightprobe.list", {}, ctx)
    assert listed["lightprobe_count"] == 1
    assert listed["lightprobes"][0]["name"] == "Probe"

    changed = dispatch_on_main(reg, "lightprobe.set", {"name": "Probe", "property": "influence_distance", "value": "4.5"}, ctx)
    assert changed["value"] == 4.5
    assert bpy.objects.get("Probe").data.influence_distance == 4.5

    visible = dispatch_on_main(reg, "lightprobe.set", {"name": "Probe", "property": "show_influence", "value": "false"}, ctx)
    assert visible["value"] is False

    report = dispatch_on_main(reg, "lightprobe.report", {"name": "Probe"}, ctx)
    assert report["lightprobe"]["properties"]["influence_distance"]["value"] == 4.5
    assert report["lightprobe"]["properties"]["show_influence"]["value"] is False


def test_create_volume_probe_reports_volume_specific_properties(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(reg, "lightprobe.create", {"type": "VOLUME", "name": "VolumeProbe"}, ctx)

    assert created["lightprobe"]["type"] == "VOLUME"
    assert created["lightprobe"]["properties"]["intensity"]["value"] == 1.0
    assert created["lightprobe"]["properties"]["resolution_x"]["value"] == 4


def test_non_light_probe_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "lightprobe.report", {"name": "Cube"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_missing_property_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Probe"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "lightprobe.set", {"name": "Probe", "property": "missing", "value": "1"}, ctx)

    assert exc.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []
