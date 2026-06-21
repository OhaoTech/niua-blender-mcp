"""Particles GUI-parity domain tests (fake-bpy)."""

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


class FakeParticleSettings:
    def __init__(self, name: str = "ParticleSettings") -> None:
        self.name = name
        self.type = "EMITTER"
        self.count = 1000
        self.frame_start = 1.0
        self.frame_end = 200.0
        self.display_percentage = 100
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("type", "ENUM"),
            FakeRnaProp("count", "INT"),
            FakeRnaProp("frame_start", "FLOAT"),
            FakeRnaProp("frame_end", "FLOAT"),
            FakeRnaProp("display_percentage", "INT"),
        )


class FakeParticleSystem:
    def __init__(self, name: str = "ParticleSystem") -> None:
        self.name = name
        self.seed = 0
        self.settings = FakeParticleSettings()
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("seed", "INT"),
            FakeRnaProp("settings", "POINTER"),
        )


class FakeParticleSystems(list):
    def __init__(self) -> None:
        super().__init__()
        self.active_index = 0

    def get(self, name: str):
        return next((psys for psys in self if psys.name == name), None)

    def add(self) -> FakeParticleSystem:
        psys = FakeParticleSystem("ParticleSystem" if not self else f"ParticleSystem.{len(self):03d}")
        self.append(psys)
        self.active_index = len(self) - 1
        return psys

    def remove_active(self) -> None:
        if self:
            self.pop(self.active_index)
            self.active_index = max(0, min(self.active_index, len(self) - 1))


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.particle_systems = FakeParticleSystems()
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

        def _particle_system_add(**kwargs):
            bpy._active_obj.particle_systems.add()

        def _particle_system_remove(**kwargs):
            bpy._active_obj.particle_systems.remove_active()

        class _ObjectOps:
            particle_system_add = _Op(log, "object.particle_system_add", on_call=_particle_system_add)
            particle_system_remove = _Op(log, "object.particle_system_remove", on_call=_particle_system_remove)

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


def _op_names(bpy: FakeBpy) -> list[str]:
    return [name for name, _ in bpy.op_calls]


def test_router_contains_particles_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "particles.systems",
        "particles.add",
        "particles.remove",
        "particles.report",
        "particles.set",
    } <= names


def test_add_and_list_particle_system(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Emitter"))
    obj.mode = "EDIT"
    reg = build_default_registry()

    added = dispatch_on_main(reg, "particles.add", {"object": "Emitter", "name": "Dust"}, ctx)

    assert added["particle_system"]["name"] == "Dust"
    assert added["particle_system"]["settings"]["name"] == "ParticleSettings"
    assert "object.particle_system_add" in _op_names(bpy)
    assert bpy.mode_calls == ["OBJECT", "EDIT"]
    assert bpy.undo_pushes == ["niua:particles.add"]

    listed = dispatch_on_main(reg, "particles.systems", {"object": "Emitter"}, ctx)
    assert listed["system_count"] == 1
    assert listed["systems"][0]["name"] == "Dust"
    assert bpy.undo_pushes == ["niua:particles.add"]


def test_report_uses_particle_system_and_settings_rna(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Emitter"))
    psys = obj.particle_systems.add()
    psys.name = "Dust"
    psys.settings.count = 123
    reg = build_default_registry()

    result = dispatch_on_main(reg, "particles.report", {"object": "Emitter", "name": "Dust"}, ctx)

    report = result["particle_system"]
    assert report["properties"]["seed"]["value"] == 0
    assert report["settings"]["properties"]["count"]["value"] == 123
    assert "rna_type" not in report["settings"]["properties"]
    assert bpy.undo_pushes == []


def test_set_particle_settings_property_from_json_value(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Emitter"))
    psys = obj.particle_systems.add()
    psys.name = "Dust"
    reg = build_default_registry()

    changed = dispatch_on_main(
        reg,
        "particles.set",
        {"object": "Emitter", "name": "Dust", "property": "count", "value": "250"},
        ctx,
    )
    assert psys.settings.count == 250
    assert changed["value"] == 250

    changed = dispatch_on_main(
        reg,
        "particles.set",
        {"object": "Emitter", "name": "Dust", "property": "settings.frame_start", "value": "12.0"},
        ctx,
    )
    assert psys.settings.frame_start == 12.0
    assert changed["value"] == 12.0
    assert bpy.undo_pushes == ["niua:particles.set", "niua:particles.set"]


def test_remove_particle_system_pushes_undo(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Emitter"))
    psys = obj.particle_systems.add()
    psys.name = "Dust"
    reg = build_default_registry()

    removed = dispatch_on_main(reg, "particles.remove", {"object": "Emitter", "name": "Dust"}, ctx)

    assert removed["system_count"] == 0
    assert list(obj.particle_systems) == []
    assert "object.particle_system_remove" in _op_names(bpy)
    assert bpy.undo_pushes == ["niua:particles.remove"]


def test_missing_particle_system_fails_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Emitter"))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "particles.set",
            {"object": "Emitter", "name": "Dust", "property": "count", "value": "1"},
            ctx,
        )

    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []
