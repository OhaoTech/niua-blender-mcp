"""Sequencer GUI-parity domain tests (fake-bpy)."""

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


class FakeStripModifier:
    def __init__(self, name: str, type: str) -> None:
        self.name = name
        self.type = type
        self.mute = False
        self.bright = 0.0
        self.contrast = 0.0
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("type", "ENUM", is_readonly=True),
            FakeRnaProp("mute", "BOOLEAN"),
            FakeRnaProp("bright", "FLOAT"),
            FakeRnaProp("contrast", "FLOAT"),
        )


class FakeStripModifiers(list):
    def new(self, name: str, type: str):
        modifier = FakeStripModifier(name, type)
        self.append(modifier)
        return modifier

    def get(self, name: str):
        return next((modifier for modifier in self if modifier.name == name), None)

    def remove(self, modifier) -> None:
        super().remove(modifier)


class FakeStrip:
    def __init__(self, name: str, type: str, channel: int, frame_start: int, length: int) -> None:
        self.name = name
        self.type = type
        self.channel = channel
        self.frame_start = frame_start
        self.frame_final_end = frame_start + length
        self.mute = False
        self.blend_type = "REPLACE"
        self.color = [0.0, 0.0, 0.0]
        self.select = False
        self.modifiers = FakeStripModifiers()
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("type", "ENUM", is_readonly=True),
            FakeRnaProp("channel", "INT"),
            FakeRnaProp("frame_start", "INT"),
            FakeRnaProp("frame_final_end", "INT", is_readonly=True),
            FakeRnaProp("mute", "BOOLEAN"),
            FakeRnaProp("blend_type", "ENUM"),
            FakeRnaProp("color", "FLOAT", is_readonly=False),
        )


class FakeStrips(list):
    def new_effect(self, name: str, type: str, channel: int, frame_start: int, length: int, **kwargs):
        strip = FakeStrip(name, type, channel, frame_start, length)
        self.append(strip)
        return strip

    def get(self, name: str):
        return next((strip for strip in self if strip.name == name), None)

    def remove(self, strip) -> None:
        super().remove(strip)


class FakeSequenceEditor:
    def __init__(self) -> None:
        self.strips = FakeStrips()
        self.active_strip = None


class FakeScene:
    def __init__(self) -> None:
        self.name = "Scene"
        self.frame_start = 1
        self.frame_end = 48
        self.sequence_editor = None
        self.objects = []

    def sequence_editor_create(self):
        if self.sequence_editor is None:
            self.sequence_editor = FakeSequenceEditor()
        return self.sequence_editor


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
        self.scene = FakeScene()
        self.op_calls: list = []
        self.undo_pushes: list[str] = []

        bpy = self

        class _Context:
            scene = self.scene
            window_manager = types.SimpleNamespace(windows=[])
            view_layer = types.SimpleNamespace(objects=types.SimpleNamespace(active=None))

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()
        log = self.op_calls

        def _strip_modifier_add(type: str, **kwargs):
            strip = bpy.context.scene.sequence_editor.active_strip
            strip.modifiers.new(name=type, type=type)

        class _SequencerOps:
            strip_modifier_add = _Op(log, "sequencer.strip_modifier_add", on_call=_strip_modifier_add)

        class _EdOps:
            @staticmethod
            def undo_push(message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(sequencer=_SequencerOps(), ed=_EdOps())

    @property
    def data(self):
        return types.SimpleNamespace(objects=types.SimpleNamespace(get=lambda name: None), materials={})


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _op_names(bpy: FakeBpy) -> list[str]:
    return [name for name, _ in bpy.op_calls]


def test_router_contains_sequencer_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "sequencer.report",
        "sequencer.strip_add",
        "sequencer.strip_remove",
        "sequencer.strip_set",
        "sequencer.modifiers",
        "sequencer.modifier_add",
        "sequencer.modifier_set",
        "sequencer.modifier_remove",
    } <= names


def test_strip_add_report_set_and_remove(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    added = dispatch_on_main(
        reg,
        "sequencer.strip_add",
        {"type": "COLOR", "name": "ColorHero", "frame_start": 5, "channel": 2},
        ctx,
    )
    assert added["strip"]["name"] == "ColorHero"
    assert added["strip"]["type"] == "COLOR"
    assert added["strip"]["channel"] == 2
    assert bpy.undo_pushes == ["niua:sequencer.strip_add"]

    report = dispatch_on_main(reg, "sequencer.report", {}, ctx)
    assert report["strip_count"] == 1
    assert report["strips"][0]["properties"]["name"]["value"] == "ColorHero"

    changed = dispatch_on_main(
        reg,
        "sequencer.strip_set",
        {"name": "ColorHero", "property": "channel", "value": "3"},
        ctx,
    )
    assert changed["value"] == 3
    assert changed["strip"]["channel"] == 3

    removed = dispatch_on_main(reg, "sequencer.strip_remove", {"name": "ColorHero"}, ctx)
    assert removed["strip_count"] == 0
    assert bpy.undo_pushes[-1] == "niua:sequencer.strip_remove"


def test_strip_modifier_add_set_list_and_remove(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "sequencer.strip_add", {"type": "COLOR", "name": "ColorHero"}, ctx)

    added = dispatch_on_main(
        reg,
        "sequencer.modifier_add",
        {"name": "ColorHero", "type": "BRIGHT_CONTRAST", "modifier_name": "Bright"},
        ctx,
    )
    assert added["modifier"]["name"] == "Bright"
    assert added["modifier"]["type"] == "BRIGHT_CONTRAST"
    assert "sequencer.strip_modifier_add" in _op_names(bpy)

    changed = dispatch_on_main(
        reg,
        "sequencer.modifier_set",
        {"name": "ColorHero", "modifier": "Bright", "property": "bright", "value": "0.25"},
        ctx,
    )
    assert changed["value"] == 0.25

    listed = dispatch_on_main(reg, "sequencer.modifiers", {"name": "ColorHero"}, ctx)
    assert listed["modifier_count"] == 1
    assert listed["modifiers"][0]["properties"]["bright"]["value"] == 0.25

    removed = dispatch_on_main(reg, "sequencer.modifier_remove", {"name": "ColorHero", "modifier": "Bright"}, ctx)
    assert removed["modifier_count"] == 0


def test_missing_strip_fails_without_undo(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "sequencer.strip_set", {"name": "Nope", "property": "channel", "value": "2"}, ctx)

    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []
