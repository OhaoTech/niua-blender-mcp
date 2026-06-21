"""API editor/source GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeRna:
    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description


class FakeOp:
    def __init__(self, name: str, description: str) -> None:
        self._rna = FakeRna(name, description)

    def poll(self) -> bool:
        return True

    def get_rna_type(self):
        return self._rna


class FakeType:
    bl_rna = FakeRna("Object", "Object data-block")


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.app = types.SimpleNamespace(background=True, version_string="5.1.1")
        self.context = types.SimpleNamespace(window_manager=types.SimpleNamespace(windows=[]))
        self.ops = types.SimpleNamespace(
            mesh=types.SimpleNamespace(primitive_cube_add=FakeOp("Add Cube", "Add a cube mesh")),
            object=types.SimpleNamespace(delete=FakeOp("Delete", "Delete selected objects")),
            ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None),
        )
        self.types = types.SimpleNamespace(Object=FakeType)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_api_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"api.report", "api.search"} <= names


def test_api_report_and_search(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    report = dispatch_on_main(reg, "api.report", {}, ctx)
    assert report["version_string"] == "5.1.1"
    assert report["operator_category_count"] >= 2
    assert "mesh" in report["operator_categories"]

    search = dispatch_on_main(reg, "api.search", {"query": "cube", "limit": 5}, ctx)
    assert search["query"] == "cube"
    assert search["results"][0]["kind"] == "operator"
    assert search["results"][0]["idname"] == "mesh.primitive_cube_add"
