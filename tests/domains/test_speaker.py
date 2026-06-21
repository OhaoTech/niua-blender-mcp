"""Speaker GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, PRECONDITION, BridgeError


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


class FakeSound:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeSpeakerData:
    def __init__(self, name: str = "Speaker") -> None:
        self.name = name
        self.id_type = "SPEAKER"
        self.users = 1
        self.use_fake_user = False
        self.use_extra_user = False
        self.tag = False
        self.muted = False
        self.sound = None
        self.volume_max = 1.0
        self.volume_min = 0.0
        self.distance_max = 100.0
        self.distance_reference = 1.0
        self.attenuation = 1.0
        self.cone_angle_outer = 360.0
        self.cone_angle_inner = 360.0
        self.cone_volume_outer = 1.0
        self.volume = 1.0
        self.pitch = 1.0
        self.animation_data = None
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("id_type", "ENUM", is_readonly=True),
            FakeRnaProp("users", "INT", is_readonly=True),
            FakeRnaProp("use_fake_user", "BOOLEAN"),
            FakeRnaProp("use_extra_user", "BOOLEAN"),
            FakeRnaProp("tag", "BOOLEAN"),
            FakeRnaProp("muted", "BOOLEAN"),
            FakeRnaProp("sound", "POINTER"),
            FakeRnaProp("volume_max", "FLOAT"),
            FakeRnaProp("volume_min", "FLOAT"),
            FakeRnaProp("distance_max", "FLOAT"),
            FakeRnaProp("distance_reference", "FLOAT"),
            FakeRnaProp("attenuation", "FLOAT"),
            FakeRnaProp("cone_angle_outer", "FLOAT"),
            FakeRnaProp("cone_angle_inner", "FLOAT"),
            FakeRnaProp("cone_volume_outer", "FLOAT"),
            FakeRnaProp("volume", "FLOAT"),
            FakeRnaProp("pitch", "FLOAT"),
            FakeRnaProp("animation_data", "POINTER", is_readonly=True),
        )


class FakeObj:
    def __init__(self, name: str, type: str = "SPEAKER", data: FakeSpeakerData | None = None) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeSpeakerData(name)
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


class FakeSpeakers(list):
    def get(self, name: str):
        return next((speaker for speaker in self if speaker.name == name), None)


class FakeSounds(list):
    def get(self, name: str):
        return next((sound for sound in self if sound.name == name), None)


class _Op:
    def __init__(self, log: list, name: str, on_call=None) -> None:
        self._log = log
        self._name = name
        self._on_call = on_call

    def poll(self) -> bool:
        return True

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))
        if self._on_call is not None:
            return self._on_call(**kwargs)
        return {"FINISHED"}


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = FakeObjects()
        self.speakers = FakeSpeakers()
        self.sounds = FakeSounds([FakeSound("Tone")])
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
            obj = FakeObj(type.title(), type=type)
            obj.location = list(location or [0.0, 0.0, 0.0])
            self.add(obj)
            return {"FINISHED"}

        class _ObjectOps:
            add = _Op(log, "object.add", on_call=_object_add)

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
        if getattr(obj, "type", None) == "SPEAKER" and getattr(obj, "data", None) is not None:
            self.speakers.append(obj.data)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        return types.SimpleNamespace(objects=self.objects, speakers=self.speakers, sounds=self.sounds)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _op_names(bpy: FakeBpy) -> list[str]:
    return [name for name, _ in bpy.op_calls]


def test_router_contains_speaker_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "speaker.create",
        "speaker.list",
        "speaker.report",
        "speaker.set",
    } <= names


def test_create_list_report_and_set_speaker(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(reg, "speaker.create", {"name": "Announcer", "location": [1, 2, 3]}, ctx)

    assert created["object"] == "Announcer"
    assert created["type"] == "SPEAKER"
    assert created["speaker"]["data"] == "Announcer"
    assert created["location"] == [1.0, 2.0, 3.0]
    assert "object.add" in _op_names(bpy)
    assert bpy.undo_pushes == ["niua:speaker.create"]

    listed = dispatch_on_main(reg, "speaker.list", {}, ctx)
    assert listed["speaker_count"] == 1
    assert listed["speakers"][0]["name"] == "Announcer"

    volume = dispatch_on_main(reg, "speaker.set", {"name": "Announcer", "property": "volume", "value": "0.5"}, ctx)
    assert volume["value"] == 0.5
    assert bpy.objects.get("Announcer").data.volume == 0.5

    muted = dispatch_on_main(reg, "speaker.set", {"name": "Announcer", "property": "muted", "value": "true"}, ctx)
    assert muted["value"] is True

    report = dispatch_on_main(reg, "speaker.report", {"name": "Announcer"}, ctx)
    assert report["speaker"]["properties"]["volume"]["value"] == 0.5
    assert report["speaker"]["properties"]["muted"]["value"] is True


def test_set_sound_pointer_by_sound_name(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Announcer", data=FakeSpeakerData("Announcer")))
    reg = build_default_registry()

    changed = dispatch_on_main(
        reg,
        "speaker.set",
        {"name": "Announcer", "property": "sound", "value": json.dumps({"sound": "Tone"})},
        ctx,
    )

    assert changed["speaker"]["sound"] == "Tone"
    assert bpy.objects.get("Announcer").data.sound.name == "Tone"


def test_non_speaker_object_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH", data=None))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "speaker.report", {"name": "Cube"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_read_only_and_missing_properties_fail_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Announcer", data=FakeSpeakerData("Announcer")))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as readonly:
        dispatch_on_main(reg, "speaker.set", {"name": "Announcer", "property": "id_type", "value": json.dumps("SOUND")}, ctx)

    with pytest.raises(BridgeError) as missing:
        dispatch_on_main(reg, "speaker.set", {"name": "Announcer", "property": "missing", "value": "1"}, ctx)

    assert readonly.value.code == PRECONDITION
    assert missing.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []
