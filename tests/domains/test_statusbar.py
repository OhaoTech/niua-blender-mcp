"""Statusbar GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeScene:
    name = "Scene"

    def statistics(self, view_layer):
        return "Objects:1 | Vertices:8"


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        status_area = types.SimpleNamespace(type="STATUSBAR", regions=[types.SimpleNamespace(type="WINDOW")])
        screen = types.SimpleNamespace(name="Layout", areas=[status_area])
        window = types.SimpleNamespace(screen=screen, workspace=types.SimpleNamespace(name="Layout"))
        self.app = types.SimpleNamespace(background=True)
        self.context = types.SimpleNamespace(
            window_manager=types.SimpleNamespace(windows=[window]),
            scene=FakeScene(),
            view_layer=types.SimpleNamespace(name="ViewLayer"),
            screen=screen,
            workspace=window.workspace,
            mode="OBJECT",
        )
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None))


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_statusbar_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"statusbar.report"} <= names


def test_statusbar_report(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    report = dispatch_on_main(reg, "statusbar.report", {}, ctx)
    assert report["area_count"] == 1
    assert report["scene_statistics"] == "Objects:1 | Vertices:8"
    assert report["mode"] == "OBJECT"
