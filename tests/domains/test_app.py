from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


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


class _Workspaces(list):
    def get(self, name: str):
        for workspace in self:
            if workspace.name == name:
                return workspace
        return None


class _Window:
    def __init__(self, context, workspace) -> None:
        self._context = context
        self._workspace = workspace

    @property
    def workspace(self):
        return self._workspace

    @workspace.setter
    def workspace(self, workspace) -> None:
        self._workspace = workspace
        self._context.workspace = workspace


class FakeAddonUtils(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("addon_utils")
        self.states = {
            "mesh_looptools": (True, True),
            "io_scene_obj": (False, False),
        }
        self._modules = [
            types.SimpleNamespace(
                __name__="mesh_looptools",
                bl_info={"name": "LoopTools", "version": (4, 9, 0), "category": "Mesh"},
            ),
            types.SimpleNamespace(
                __name__="io_scene_obj",
                bl_info={"name": "Wavefront OBJ", "version": (1, 0, 0), "category": "Import-Export"},
            ),
        ]

    def modules(self):
        return list(self._modules)

    def check(self, module: str):
        return self.states.get(module, (False, False))


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.app = types.SimpleNamespace(version_string="5.1.1", version=(5, 1, 1), background=False)
        workspaces = _Workspaces(
            [
                types.SimpleNamespace(name="Layout"),
                types.SimpleNamespace(name="Modeling"),
                types.SimpleNamespace(name="Scripting"),
            ]
        )
        self.data = types.SimpleNamespace(filepath="", is_dirty=False, workspaces=workspaces)
        render = types.SimpleNamespace(engine="BLENDER_EEVEE")
        scene = types.SimpleNamespace(name="Scene", render=render)
        preferences = types.SimpleNamespace(
            view=types.SimpleNamespace(ui_scale=1.25, show_tooltips=True),
            edit=types.SimpleNamespace(use_global_undo=True, undo_steps=32),
            filepaths=types.SimpleNamespace(temporary_directory="/tmp", render_output_directory="//"),
            system=types.SimpleNamespace(memory_cache_limit=4096),
        )
        self.context = types.SimpleNamespace(
            scene=scene,
            workspace=workspaces[0],
            window=None,
            preferences=preferences,
        )
        self.context.window = _Window(self.context, workspaces[0])
        self.addon_utils = FakeAddonUtils()

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

        def _addon_enable(kwargs):
            module = kwargs["module"]
            bpy.addon_utils.states[module] = (True, True)

        def _addon_disable(kwargs):
            module = kwargs["module"]
            bpy.addon_utils.states[module] = (False, False)

        class _WmOps:
            read_factory_settings = _Op(bpy.op_calls, "wm.read_factory_settings", side=_new)
            open_mainfile = _Op(bpy.op_calls, "wm.open_mainfile", side=_open)
            save_mainfile = _Op(bpy.op_calls, "wm.save_mainfile", side=_save)
            save_as_mainfile = _Op(bpy.op_calls, "wm.save_as_mainfile", side=_save_as)
            revert_mainfile = _Op(bpy.op_calls, "wm.revert_mainfile", side=lambda kw: setattr(bpy.data, "is_dirty", False))
            save_userpref = _Op(bpy.op_calls, "wm.save_userpref")

        class _EdOps:
            undo = _Op(bpy.op_calls, "ed.undo")
            redo = _Op(bpy.op_calls, "ed.redo")

            def undo_push(self, message: str = "", **kw):
                bpy.undo_pushes.append(message)

        class _PreferencesOps:
            addon_enable = _Op(bpy.op_calls, "preferences.addon_enable", side=_addon_enable)
            addon_disable = _Op(bpy.op_calls, "preferences.addon_disable", side=_addon_disable)

        self.ops = types.SimpleNamespace(wm=_WmOps(), ed=_EdOps(), preferences=_PreferencesOps())


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.setitem(sys.modules, "addon_utils", bpy.addon_utils)
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


def test_undo_and_redo_call_ed_ops_without_undo_push(env):
    ctx, bpy = env
    reg = build_default_registry()
    assert dispatch_on_main(reg, "app.undo", {}, ctx) == {"ok": True, "applied": ["ed.undo"]}
    assert dispatch_on_main(reg, "app.redo", {}, ctx) == {"ok": True, "applied": ["ed.redo"]}
    assert _names(bpy.op_calls) == ["ed.undo", "ed.redo"]
    assert bpy.undo_pushes == []


def test_workspaces_lists_and_switches_active_workspace(env):
    ctx, bpy = env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "app.workspaces", {}, ctx)
    assert out == {"active": "Layout", "workspaces": ["Layout", "Modeling", "Scripting"]}

    switched = dispatch_on_main(reg, "app.workspace_set", {"name": "Modeling"}, ctx)
    assert switched == {"active": "Modeling", "workspaces": ["Layout", "Modeling", "Scripting"]}
    assert bpy.context.window.workspace.name == "Modeling"
    assert bpy.context.workspace.name == "Modeling"

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "app.workspace_set", {"name": "Compositing"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_addons_lists_and_toggles_modules(env):
    ctx, bpy = env
    reg = build_default_registry()
    out = dispatch_on_main(reg, "app.addons", {}, ctx)
    assert out["addons"][0] == {
        "module": "io_scene_obj",
        "name": "Wavefront OBJ",
        "version": [1, 0, 0],
        "category": "Import-Export",
        "enabled": False,
        "loaded": False,
    }
    assert out["addons"][1]["module"] == "mesh_looptools"
    assert out["enabled"] == ["mesh_looptools"]

    enabled = dispatch_on_main(reg, "app.addon_enable", {"module": "io_scene_obj"}, ctx)
    assert enabled["module"] == "io_scene_obj"
    assert enabled["enabled"] is True
    assert bpy.op_calls[-1] == ("preferences.addon_enable", {"module": "io_scene_obj"})

    disabled = dispatch_on_main(reg, "app.addon_disable", {"module": "mesh_looptools"}, ctx)
    assert disabled["module"] == "mesh_looptools"
    assert disabled["enabled"] is False
    assert bpy.op_calls[-1] == ("preferences.addon_disable", {"module": "mesh_looptools"})

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "app.addon_enable", {"module": "missing_addon"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_preferences_summary_and_save(env):
    ctx, bpy = env
    reg = build_default_registry()
    summary = dispatch_on_main(reg, "app.preferences_summary", {}, ctx)
    assert summary == {
        "view": {"ui_scale": 1.25, "show_tooltips": True},
        "edit": {"use_global_undo": True, "undo_steps": 32},
        "filepaths": {"temporary_directory": "/tmp", "render_output_directory": "//"},
        "system": {"memory_cache_limit": 4096},
    }

    saved = dispatch_on_main(reg, "app.preferences_save", {}, ctx)
    assert saved == {"ok": True, "applied": ["wm.save_userpref"]}
    assert bpy.op_calls[-1] == ("wm.save_userpref", {})
