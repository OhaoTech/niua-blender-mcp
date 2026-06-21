"""Topbar GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeRnaType:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


class FakeOp:
    def __init__(self, name: str, description: str = "") -> None:
        self._rna = FakeRnaType(name, description)

    def poll(self) -> bool:
        return True

    def get_rna_type(self):
        return self._rna


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        topbar_area = types.SimpleNamespace(type="TOPBAR", regions=[types.SimpleNamespace(type="WINDOW")])
        screen = types.SimpleNamespace(name="Layout", areas=[topbar_area])
        workspace = types.SimpleNamespace(name="Layout")
        window = types.SimpleNamespace(screen=screen, workspace=workspace)
        self.app = types.SimpleNamespace(background=True)
        self.context = types.SimpleNamespace(
            window_manager=types.SimpleNamespace(windows=[window]),
            scene=types.SimpleNamespace(name="Scene"),
            screen=screen,
            workspace=workspace,
            mode="OBJECT",
        )
        self.ops = types.SimpleNamespace(
            mesh=types.SimpleNamespace(primitive_cube_add=FakeOp("Add Cube", "Add a cube mesh")),
            wm=types.SimpleNamespace(search_operator=FakeOp("Search Menu")),
            ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None),
        )


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_topbar_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"topbar.report", "topbar.command_search"} <= names


def test_topbar_report_and_command_search(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    report = dispatch_on_main(reg, "topbar.report", {}, ctx)
    assert report["workspace"] == "Layout"
    assert report["scene"] == "Scene"
    assert report["area_count"] == 1

    search = dispatch_on_main(reg, "topbar.command_search", {"query": "cube", "limit": 5}, ctx)
    assert search["query"] == "cube"
    assert search["results"][0]["idname"] == "mesh.primitive_cube_add"
    assert search["results"][0]["name"] == "Add Cube"
