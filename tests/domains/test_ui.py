from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class _Op:
    def __init__(self, name: str, poll_ok: bool = True) -> None:
        self.name = name
        self.poll_ok = poll_ok
        self.calls: list[dict] = []

    def poll(self) -> bool:
        return self.poll_ok

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))


class FakeRegion:
    def __init__(self, type: str, x: int, y: int, width: int, height: int) -> None:
        self.type = type
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class FakeArea:
    def __init__(self, type: str, x: int, y: int, width: int, height: int) -> None:
        self.type = type
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.regions = [
            FakeRegion("HEADER", x, y + height - 24, width, 24),
            FakeRegion("WINDOW", x, y, width, height - 24),
        ]


class FakeWindow:
    def __init__(self, screen, workspace) -> None:
        self.screen = screen
        self.workspace = workspace


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        workspace = types.SimpleNamespace(name="Layout")
        areas = [
            FakeArea("OUTLINER", 0, 0, 300, 600),
            FakeArea("VIEW_3D", 300, 0, 900, 600),
        ]
        screen = types.SimpleNamespace(name="Layout", areas=areas)
        window = FakeWindow(screen, workspace)
        self.app = types.SimpleNamespace(background=True, version_string="5.1.1")
        @contextmanager
        def temp_override(**kw):
            yield

        self.context = types.SimpleNamespace(
            window=window,
            screen=screen,
            workspace=workspace,
            area=areas[1],
            window_manager=types.SimpleNamespace(windows=[window]),
            temp_override=temp_override,
        )
        self.ops = types.SimpleNamespace(
            screen=types.SimpleNamespace(screenshot=_Op("screen.screenshot", poll_ok=False)),
            wm=types.SimpleNamespace(redraw_timer=_Op("wm.redraw_timer", poll_ok=True)),
            ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None),
        )


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_exposes_ui_state_tools():
    names = {spec.name for spec in build_router().specs()}
    assert {"ui.state", "ui.windows"} <= names


def test_ui_state_reports_background_windows_and_capabilities(env):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "ui.state", {}, ctx)

    assert out["background"] is True
    assert out["window_count"] == 1
    assert out["active_window"] == {"index": 0, "screen": "Layout", "workspace": "Layout"}
    assert out["capabilities"]["context_override"]["available"] is True
    assert out["capabilities"]["screen_screenshot"]["available"] is False
    assert out["capabilities"]["redraw"]["available"] is True
    assert out["capabilities"]["keyboard_events"]["available"] is False
    assert out["capabilities"]["mouse_events"]["available"] is False


def test_ui_windows_reports_areas_regions_and_geometry(env):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "ui.windows", {}, ctx)

    assert out["background"] is True
    assert out["windows"][0]["index"] == 0
    assert out["windows"][0]["screen"] == "Layout"
    assert [area["type"] for area in out["windows"][0]["areas"]] == ["OUTLINER", "VIEW_3D"]
    view = out["windows"][0]["areas"][1]
    assert view["rect"] == {"x": 300, "y": 0, "width": 900, "height": 600}
    assert view["regions"][1] == {
        "index": 1,
        "type": "WINDOW",
        "rect": {"x": 300, "y": 0, "width": 900, "height": 576},
    }
