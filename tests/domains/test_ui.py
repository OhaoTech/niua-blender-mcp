from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, BridgeError


class _NamedList(list):
    def get(self, name: str):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class FakeProp:
    def __init__(self, identifier: str, type: str = "FLOAT") -> None:
        self.identifier = identifier
        self.type = type
        self.is_array = False
        self.array_length = 0


class FakeRnaType:
    def __init__(self, props) -> None:
        self.properties = list(props)


class _Op:
    def __init__(self, name: str, poll_ok: bool = True, props=None) -> None:
        self.name = name
        self.poll_ok = poll_ok
        self.props = list(props or [])
        self.calls: list[dict] = []

    def poll(self) -> bool:
        return self.poll_ok

    def get_rna_type(self):
        return FakeRnaType(self.props + [FakeProp("rna_type", "POINTER")])

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.name == "screen.screenshot" and kwargs.get("filepath"):
            Path(kwargs["filepath"]).write_bytes(b"fake")


class _MissingOp:
    def get_rna_type(self):
        raise AttributeError("missing")


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


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
        self.override_calls: list[dict] = []
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []
        cube = FakeObj("Cube")
        cube.select_set(True)
        self.objects = _NamedList([cube])
        self._active_obj = cube
        self.scene = types.SimpleNamespace(name="Scene", objects=self.objects)
        workspace = types.SimpleNamespace(name="Layout")
        areas = [
            FakeArea("OUTLINER", 0, 0, 300, 600),
            FakeArea("VIEW_3D", 300, 0, 900, 600),
        ]
        screen = types.SimpleNamespace(name="Layout", areas=areas)
        window = FakeWindow(screen, workspace)
        self.app = types.SimpleNamespace(background=True, version_string="5.1.1")
        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

            @active.setter
            def active(self_inner, value):
                bpy._active_obj = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        @contextmanager
        def temp_override(**kw):
            self.override_calls.append(dict(kw))
            yield

        class _Context:
            @property
            def object(self_inner):
                return bpy._active_obj

            @property
            def selected_objects(self_inner):
                return [obj for obj in bpy.objects if obj.select_get()]

        self.context = _Context()
        self.context.window = window
        self.context.screen = screen
        self.context.workspace = workspace
        self.context.area = areas[1]
        self.context.scene = self.scene
        self.context.view_layer = self.view_layer
        self.context.window_manager = types.SimpleNamespace(windows=[window])
        self.context.temp_override = temp_override

        bevel = _Op(
            "mesh.bevel",
            props=[FakeProp("offset", "FLOAT"), FakeProp("segments", "INT")],
        )

        class _ObjectOps:
            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(
            screen=types.SimpleNamespace(screenshot=_Op("screen.screenshot", poll_ok=False)),
            wm=types.SimpleNamespace(redraw_timer=_Op("wm.redraw_timer", poll_ok=True)),
            mesh=types.SimpleNamespace(bevel=bevel, missing=_MissingOp()),
            object=_ObjectOps(),
            ed=_EdOps(),
        )
        self.data = types.SimpleNamespace(objects=self.objects)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_exposes_ui_state_tools():
    names = {spec.name for spec in build_router().specs()}
    assert {"ui.state", "ui.windows"} <= names


def test_router_exposes_ui_operator_tools():
    names = {spec.name for spec in build_router().specs()}
    assert {"ui.operator_poll", "ui.operator_invoke"} <= names


def test_router_exposes_ui_screenshot_and_redraw_tools():
    names = {spec.name for spec in build_router().specs()}
    assert {"ui.screenshot", "ui.redraw"} <= names


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


def test_operator_poll_uses_requested_area_override(env):
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "ui.operator_poll",
        {"idname": "mesh.bevel", "area": "VIEW_3D", "region": "WINDOW"},
        ctx,
    )

    assert out["idname"] == "mesh.bevel"
    assert out["available"] is True
    assert out["ui_context"]["override"] is True
    assert out["ui_context"]["area"] == {"index": 1, "type": "VIEW_3D"}
    assert bpy.override_calls[-1]["area"].type == "VIEW_3D"
    assert bpy.override_calls[-1]["region"].type == "WINDOW"


def test_operator_poll_require_area_missing_returns_unavailable(env):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "ui.operator_poll",
        {"idname": "mesh.bevel", "area": "NODE_EDITOR", "require_area": True},
        ctx,
    )

    assert out["idname"] == "mesh.bevel"
    assert out["available"] is False
    assert "area not found" in out["reason"]
    assert out["ui_context"]["override"] is False


def test_operator_invoke_runs_with_args_context_and_undo(env):
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "ui.operator_invoke",
        {
            "idname": "mesh.bevel",
            "args": json.dumps({"offset": 0.2, "segments": 3, "bogus": 9}),
            "object": "Cube",
            "mode": "EDIT",
            "select": json.dumps(["Cube"]),
            "area": "VIEW_3D",
        },
        ctx,
    )

    assert out["operator"] == "mesh.bevel"
    assert out["args"] == {"offset": 0.2, "segments": 3}
    assert out["dropped_args"] == ["bogus"]
    assert out["ui_context"]["override"] is True
    assert bpy.ops.mesh.bevel.calls == [{"offset": 0.2, "segments": 3}]
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["mcp:ui.operator_invoke"]


def test_operator_invoke_unknown_operator_and_bad_json_are_clean_errors(env):
    ctx, _bpy = env
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "ui.operator_invoke", {"idname": "mesh.missing"}, ctx)
    assert exc.value.code == NOT_FOUND

    with pytest.raises(BridgeError) as exc2:
        dispatch_on_main(reg, "ui.operator_invoke", {"idname": "mesh.bevel", "args": "{nope"}, ctx)
    assert exc2.value.code == INVALID_PARAMS


def test_screenshot_returns_unavailable_when_operator_poll_fails(env, tmp_path):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "ui.screenshot", {"path": str(tmp_path / "shot.png")}, ctx)

    assert out["available"] is False
    assert "screen.screenshot" in out["reason"]


def test_screenshot_success_returns_file_metadata(env, tmp_path):
    ctx, bpy = env
    bpy.ops.screen.screenshot.poll_ok = True
    reg = build_default_registry()
    path = tmp_path / "shot.png"

    out = dispatch_on_main(reg, "ui.screenshot", {"path": str(path), "full": True}, ctx)

    assert out == {"available": True, "path": str(path), "size": 4, "applied": ["screen.screenshot"]}
    assert bpy.ops.screen.screenshot.calls == [{"filepath": str(path), "full": True}]


def test_redraw_returns_unavailable_when_operator_poll_fails(env):
    ctx, bpy = env
    bpy.ops.wm.redraw_timer.poll_ok = False
    reg = build_default_registry()

    out = dispatch_on_main(reg, "ui.redraw", {}, ctx)

    assert out["available"] is False
    assert "wm.redraw_timer" in out["reason"]


def test_redraw_success_calls_redraw_operator(env):
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "ui.redraw", {"type": "DRAW_WIN", "iterations": 2}, ctx)

    assert out == {
        "available": True,
        "applied": ["wm.redraw_timer"],
        "args": {"type": "DRAW_WIN", "iterations": 2},
    }
    assert bpy.ops.wm.redraw_timer.calls == [{"type": "DRAW_WIN", "iterations": 2}]
