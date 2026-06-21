"""Script space GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeOp:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def poll(self) -> bool:
        return True

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {"FINISHED"}


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        script_space = types.SimpleNamespace(type="SCRIPT")
        script_area = types.SimpleNamespace(
            type="SCRIPT",
            spaces=types.SimpleNamespace(active=script_space),
            regions=[types.SimpleNamespace(type="WINDOW")],
        )
        screen = types.SimpleNamespace(name="Layout", areas=[script_area])
        window = types.SimpleNamespace(screen=screen, workspace=types.SimpleNamespace(name="Layout"))
        self.python_file_run = FakeOp()
        self.reload = FakeOp()
        self.app = types.SimpleNamespace(background=True, version_string="5.1.1")
        self.context = types.SimpleNamespace(
            window_manager=types.SimpleNamespace(windows=[window]),
            preferences=types.SimpleNamespace(
                filepaths=types.SimpleNamespace(
                    use_scripts_auto_execute=True,
                    script_directories=[
                        types.SimpleNamespace(name="Studio", directory="/studio/scripts")
                    ],
                )
            ),
            screen=screen,
            workspace=window.workspace,
        )
        self.ops = types.SimpleNamespace(
            script=types.SimpleNamespace(
                python_file_run=self.python_file_run,
                reload=self.reload,
                execute_preset=FakeOp(),
            ),
            ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None),
        )
        self.utils = types.SimpleNamespace(
            script_path_user=lambda: "/user/scripts",
            script_paths=lambda: ["/system/scripts", "/user/scripts"],
            script_paths_pref=lambda: ["/pref/scripts"],
        )


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_script_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"script.report", "script.paths", "script.run_file", "script.reload"} <= names


def test_script_report_and_paths(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    report = dispatch_on_main(reg, "script.report", {}, ctx)
    assert report["area_count"] == 1
    assert report["preferences"]["use_scripts_auto_execute"] is True
    assert report["operators"]["python_file_run"]["available"] is True

    paths = dispatch_on_main(reg, "script.paths", {}, ctx)
    assert "/system/scripts" in paths["script_paths"]
    assert paths["script_directories"][0]["name"] == "Studio"


def test_script_run_file_and_reload_use_gui_operators(env, tmp_path) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    path = tmp_path / "hello.py"
    path.write_text("x = 1\n", encoding="utf-8")

    result = dispatch_on_main(reg, "script.run_file", {"path": str(path)}, ctx)
    assert result["path"] == str(path)
    assert result["applied"] == ["script.python_file_run"]
    assert bpy.python_file_run.calls == [{"filepath": str(path)}]

    reloaded = dispatch_on_main(reg, "script.reload", {}, ctx)
    assert reloaded["applied"] == ["script.reload"]
    assert bpy.reload.calls == [{}]
