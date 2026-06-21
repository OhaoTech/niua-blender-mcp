"""Project editor GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeOp:
    def poll(self) -> bool:
        return True


class FakeBpy(types.ModuleType):
    def __init__(self, root: str, filepath: str) -> None:
        super().__init__("bpy")
        project_space = types.SimpleNamespace(
            type="PROJECT",
            show_region_ui=True,
            active_section="General",
        )
        project_area = types.SimpleNamespace(
            type="PROJECT",
            spaces=types.SimpleNamespace(active=project_space),
            regions=[types.SimpleNamespace(type="WINDOW")],
        )
        screen = types.SimpleNamespace(name="Layout", areas=[project_area])
        window = types.SimpleNamespace(screen=screen, workspace=types.SimpleNamespace(name="Layout"))
        self.app = types.SimpleNamespace(background=True)
        self.data = types.SimpleNamespace(
            filepath=filepath,
            project=types.SimpleNamespace(name="Hero", root_path=root, is_dirty=True),
        )
        self.context = types.SimpleNamespace(
            window_manager=types.SimpleNamespace(windows=[window]),
            preferences=types.SimpleNamespace(use_project_auto_save=True),
            screen=screen,
            workspace=window.workspace,
        )
        self.ops = types.SimpleNamespace(
            project=types.SimpleNamespace(
                new_project=FakeOp(),
                save_project=FakeOp(),
                open_blend_in_project=FakeOp(),
            ),
            ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None),
        )


@pytest.fixture()
def env(monkeypatch, tmp_path):
    root = tmp_path / "HeroProject"
    config_dir = root / ".blender_project"
    config_dir.mkdir(parents=True)
    (config_dir / "project.toml").write_text('name = "Hero"\n', encoding="utf-8")
    blend = root / "hero.blend"
    blend.write_text("blend placeholder", encoding="utf-8")
    bpy = FakeBpy(str(root), str(blend))
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_project_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"project.report", "project.files", "project.settings"} <= names


def test_project_report_files_and_settings(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    report = dispatch_on_main(reg, "project.report", {}, ctx)
    assert report["project"]["name"] == "Hero"
    assert report["project"]["is_dirty"] is True
    assert report["area_count"] == 1
    assert report["operators"]["save_project"]["available"] is True

    files = dispatch_on_main(reg, "project.files", {}, ctx)
    assert files["available"] is True
    assert files["config"]["exists"] is True
    assert "hero.blend" in files["blend_files"]

    settings = dispatch_on_main(reg, "project.settings", {}, ctx)
    assert settings["preferences"]["use_project_auto_save"] is True
    assert settings["config"]["data"]["name"] == "Hero"
