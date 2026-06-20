from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, PRECONDITION, BridgeError


class _Op:
    def __init__(self, log: list, name: str, side=None) -> None:
        self._log = log
        self._name = name
        self._side = side

    def poll(self) -> bool:
        return True

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))
        if self._side is not None:
            self._side(kwargs)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.app = types.SimpleNamespace(version_string="5.1.1", version=(5, 1, 1), background=False)
        self.data = types.SimpleNamespace(filepath="", is_dirty=False)
        render = types.SimpleNamespace(engine="BLENDER_EEVEE")
        scene = types.SimpleNamespace(name="Scene", render=render)
        workspace = types.SimpleNamespace(name="Layout")
        self.context = types.SimpleNamespace(scene=scene, workspace=workspace)

        bpy = self

        def _new(kwargs):
            bpy.data.filepath = ""
            bpy.data.is_dirty = False

        def _open(kwargs):
            bpy.data.filepath = kwargs["filepath"]
            bpy.data.is_dirty = False

        def _save(kwargs):
            if kwargs.get("filepath"):
                bpy.data.filepath = kwargs["filepath"]
            bpy.data.is_dirty = False

        def _save_as(kwargs):
            if not kwargs.get("copy"):
                bpy.data.filepath = kwargs["filepath"]
                bpy.data.is_dirty = False

        class _WmOps:
            read_factory_settings = _Op(bpy.op_calls, "wm.read_factory_settings", side=_new)
            open_mainfile = _Op(bpy.op_calls, "wm.open_mainfile", side=_open)
            save_mainfile = _Op(bpy.op_calls, "wm.save_mainfile", side=_save)
            save_as_mainfile = _Op(bpy.op_calls, "wm.save_as_mainfile", side=_save_as)
            revert_mainfile = _Op(bpy.op_calls, "wm.revert_mainfile", side=lambda kw: setattr(bpy.data, "is_dirty", False))

        class _EdOps:
            def undo_push(self, message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(wm=_WmOps(), ed=_EdOps())


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _names(log):
    return [name for name, _ in log]


def test_app_info_reports_file_and_runtime_state(env):
    ctx, bpy = env
    bpy.data.filepath = "/tmp/scene.blend"
    bpy.data.is_dirty = True
    reg = build_default_registry()
    out = dispatch_on_main(reg, "app.info", {}, ctx)
    assert out["version_string"] == "5.1.1"
    assert out["background"] is False
    assert out["filepath"] == "/tmp/scene.blend"
    assert out["is_saved"] is True
    assert out["is_dirty"] is True
    assert out["scene"] == "Scene"
    assert out["workspace"] == "Layout"
    assert out["render_engine"] == "BLENDER_EEVEE"


def test_file_new_requires_force_when_dirty(env):
    ctx, bpy = env
    bpy.data.filepath = "/tmp/dirty.blend"
    bpy.data.is_dirty = True
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "app.file_new", {}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.op_calls == []


def test_file_new_runs_factory_settings_with_force(env):
    ctx, bpy = env
    bpy.data.filepath = "/tmp/dirty.blend"
    bpy.data.is_dirty = True
    reg = build_default_registry()
    out = dispatch_on_main(reg, "app.file_new", {"force": True}, ctx)
    assert _names(bpy.op_calls) == ["wm.read_factory_settings"]
    assert bpy.op_calls[0][1] == {"use_empty": True}
    assert out["filepath"] == ""
    assert out["is_dirty"] is False


def test_file_open_requires_absolute_path_and_force_when_dirty(env, tmp_path):
    ctx, bpy = env
    bpy.data.is_dirty = True
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "app.file_open", {"path": "relative.blend", "force": True}, ctx)
    assert exc.value.code == INVALID_PARAMS

    p = tmp_path / "scene.blend"
    p.write_bytes(b"fake blend")
    path = str(p)
    with pytest.raises(BridgeError) as exc2:
        dispatch_on_main(reg, "app.file_open", {"path": path}, ctx)
    assert exc2.value.code == PRECONDITION


def test_file_open_calls_open_mainfile(env, tmp_path):
    ctx, bpy = env
    p = tmp_path / "scene.blend"
    p.write_bytes(b"fake blend")
    path = str(p)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "app.file_open", {"path": path}, ctx)
    assert _names(bpy.op_calls) == ["wm.open_mainfile"]
    assert bpy.op_calls[0][1] == {"filepath": path, "load_ui": False}
    assert out["filepath"] == path


def test_file_save_requires_path_when_unsaved(env):
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "app.file_save", {}, ctx)
    assert exc.value.code == INVALID_PARAMS


def test_file_save_existing_uses_save_mainfile(env):
    ctx, bpy = env
    bpy.data.filepath = "/tmp/existing.blend"
    bpy.data.is_dirty = True
    reg = build_default_registry()
    out = dispatch_on_main(reg, "app.file_save", {}, ctx)
    assert _names(bpy.op_calls) == ["wm.save_mainfile"]
    assert out["filepath"] == "/tmp/existing.blend"
    assert out["is_dirty"] is False


def test_file_save_as_and_copy_use_save_as_mainfile(env, tmp_path):
    ctx, bpy = env
    original = str(tmp_path / "original.blend")
    target = str(tmp_path / "target.blend")
    copy = str(tmp_path / "copy.blend")
    bpy.data.filepath = original
    reg = build_default_registry()

    out = dispatch_on_main(reg, "app.file_save_as", {"path": target}, ctx)
    assert out["filepath"] == target
    assert bpy.op_calls[-1] == ("wm.save_as_mainfile", {"filepath": target})

    out2 = dispatch_on_main(reg, "app.file_save_copy", {"path": copy}, ctx)
    assert out2["filepath"] == target
    assert bpy.op_calls[-1] == ("wm.save_as_mainfile", {"filepath": copy, "copy": True})


def test_file_revert_requires_force_and_saved_file(env):
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "app.file_revert", {"force": True}, ctx)
    assert exc.value.code == PRECONDITION

    bpy.data.filepath = "/tmp/existing.blend"
    bpy.data.is_dirty = True
    with pytest.raises(BridgeError) as exc2:
        dispatch_on_main(reg, "app.file_revert", {}, ctx)
    assert exc2.value.code == PRECONDITION

    out = dispatch_on_main(reg, "app.file_revert", {"force": True}, ctx)
    assert _names(bpy.op_calls) == ["wm.revert_mainfile"]
    assert out["is_dirty"] is False
