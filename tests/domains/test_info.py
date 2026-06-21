"""Info editor GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeOp:
    def __init__(self, name: str) -> None:
        self.name = name

    def poll(self) -> bool:
        return True


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        info_area = types.SimpleNamespace(type="INFO", regions=[types.SimpleNamespace(type="WINDOW")])
        screen = types.SimpleNamespace(name="Layout", areas=[info_area])
        window = types.SimpleNamespace(screen=screen, workspace=types.SimpleNamespace(name="Layout"))
        self.app = types.SimpleNamespace(background=True)
        self.context = types.SimpleNamespace(
            window_manager=types.SimpleNamespace(windows=[window]),
            scene=types.SimpleNamespace(name="Scene"),
            screen=screen,
            workspace=window.workspace,
        )
        self.ops = types.SimpleNamespace(
            info=types.SimpleNamespace(
                report_copy=FakeOp("report_copy"),
                report_delete=FakeOp("report_delete"),
                report_replay=FakeOp("report_replay"),
            ),
            ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None),
        )


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_info_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"info.report", "info.messages"} <= names


def test_info_report_and_messages(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    report = dispatch_on_main(reg, "info.report", {}, ctx)
    assert report["background"] is True
    assert report["area_count"] == 1
    assert report["operators"]["report_copy"]["available"] is True

    messages = dispatch_on_main(reg, "info.messages", {"limit": 10}, ctx)
    assert messages["available"] is False
    assert messages["limit"] == 10
    assert messages["messages"] == []
