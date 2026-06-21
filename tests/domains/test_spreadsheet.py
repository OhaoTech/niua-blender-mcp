"""Spreadsheet GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeAttribute:
    def __init__(self, name: str, domain: str, data_type: str, values: list[object]) -> None:
        self.name = name
        self.domain = domain
        self.data_type = data_type
        self.data = [types.SimpleNamespace(value=value) for value in values]


class FakeMesh:
    def __init__(self) -> None:
        self.vertices = [
            types.SimpleNamespace(co=[0.0, 0.0, 0.0]),
            types.SimpleNamespace(co=[1.0, 2.0, 3.0]),
        ]
        self.edges = [types.SimpleNamespace(vertices=[0, 1])]
        self.polygons = [
            types.SimpleNamespace(vertices=[0, 1], material_index=0, loop_start=0, loop_total=2)
        ]
        self.loops = [
            types.SimpleNamespace(vertex_index=0, edge_index=0),
            types.SimpleNamespace(vertex_index=1, edge_index=0),
        ]
        self.attributes = [FakeAttribute("weight", "POINT", "FLOAT", [0.25, 0.75])]


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        spreadsheet_space = types.SimpleNamespace(
            type="SPREADSHEET",
            show_internal_attributes=True,
            use_filter=False,
            show_only_selected=False,
            is_pinned=False,
            geometry_component_type="MESH",
            attribute_domain="POINT",
            object_eval_state="EVALUATED",
            tables=[],
            row_filters=[],
        )
        spreadsheet_area = types.SimpleNamespace(
            type="SPREADSHEET",
            spaces=types.SimpleNamespace(active=spreadsheet_space),
            regions=[types.SimpleNamespace(type="WINDOW")],
        )
        screen = types.SimpleNamespace(name="Layout", areas=[spreadsheet_area])
        window = types.SimpleNamespace(screen=screen, workspace=types.SimpleNamespace(name="Layout"))
        obj = types.SimpleNamespace(name="SheetMesh", type="MESH", data=FakeMesh())
        objects = {"SheetMesh": obj}
        self.app = types.SimpleNamespace(background=True)
        self.data = types.SimpleNamespace(objects=types.SimpleNamespace(get=objects.get))
        self.context = types.SimpleNamespace(
            window_manager=types.SimpleNamespace(windows=[window]),
            object=obj,
            active_object=obj,
            screen=screen,
            workspace=window.workspace,
        )
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None))


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_spreadsheet_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"spreadsheet.report", "spreadsheet.columns", "spreadsheet.rows"} <= names


def test_spreadsheet_report_columns_and_rows(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    report = dispatch_on_main(reg, "spreadsheet.report", {"object": "SheetMesh"}, ctx)
    assert report["object"] == "SheetMesh"
    assert report["component"] == "POINT"
    assert report["row_count"] == 2
    assert report["area_count"] == 1
    assert report["spaces"][0]["show_internal_attributes"] is True

    columns = dispatch_on_main(reg, "spreadsheet.columns", {"object": "SheetMesh"}, ctx)
    names = {column["name"] for column in columns["columns"]}
    assert {"index", "position", "weight"} <= names

    rows = dispatch_on_main(
        reg,
        "spreadsheet.rows",
        {"object": "SheetMesh", "component": "POINT", "limit": 1, "offset": 1},
        ctx,
    )
    assert rows["total"] == 2
    assert rows["offset"] == 1
    assert rows["rows"] == [{"index": 1, "position": [1.0, 2.0, 3.0], "weight": 0.75}]
