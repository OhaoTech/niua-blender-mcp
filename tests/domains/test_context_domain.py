from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import PRECONDITION, BridgeError


class _NamedList(list):
    def get(self, name: str):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class FakeObj:
    def __init__(self, name: str, obj_type: str = "MESH") -> None:
        self.name = name
        self.type = obj_type
        self.mode = "OBJECT"
        self.hide_viewport = False
        self.hide_select = False
        self.hide_render = False
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected

    def visible_get(self) -> bool:
        return not self.hide_viewport


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self._active_obj = None
        cube = FakeObj("Cube")
        sphere = FakeObj("Sphere")
        cube.select_set(True)
        self._active_obj = cube
        self.objects = _NamedList([cube, sphere])
        scene = types.SimpleNamespace(name="Scene", objects=self.objects)

        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

            @active.setter
            def active(self_inner, value):
                bpy._active_obj = value

        self.view_layer = types.SimpleNamespace(name="ViewLayer", objects=_Objects())
        self.workspace = types.SimpleNamespace(name="Layout")
        self.tool_settings = types.SimpleNamespace(mesh_select_mode=[True, False, False])
        self.scene = scene
        self.mode_calls: list[str] = []
        self.mode_poll_ok = True
        self.mode_raise = False

        class _Context:
            scene = self.scene
            view_layer = self.view_layer
            workspace = self.workspace
            tool_settings = self.tool_settings

            @property
            def object(self_inner):
                return bpy._active_obj

            @property
            def mode(self_inner):
                active = bpy._active_obj
                if active is not None and active.mode == "EDIT":
                    return "EDIT_MESH"
                return active.mode if active is not None else "OBJECT"

            @property
            def selected_objects(self_inner):
                return [obj for obj in bpy.objects if obj.select_get()]

            window_manager = types.SimpleNamespace(windows=[])

        self.context = _Context()
        self.data = types.SimpleNamespace(objects=self.objects)
        class _ModeSet:
            def poll(self_inner):
                return bpy.mode_poll_ok

            def __call__(self_inner, mode="OBJECT", **kw):
                if bpy.mode_raise:
                    raise RuntimeError("mode context incorrect")
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        self.ops = types.SimpleNamespace(
            ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None),
            object=types.SimpleNamespace(mode_set=_ModeSet()),
        )

    def add_area(self, area_type: str = "VIEW_3D") -> None:
        region = types.SimpleNamespace(type="WINDOW")
        area = types.SimpleNamespace(type=area_type, regions=[region])
        screen = types.SimpleNamespace(name="Main", areas=[area])
        window = types.SimpleNamespace(screen=screen)
        self.context.window_manager.windows.append(window)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_context_info_reports_active_selection_modes_and_areas(env):
    ctx, bpy = env
    bpy.add_area("VIEW_3D")
    reg = build_default_registry()

    out = dispatch_on_main(reg, "context.info", {}, ctx)

    assert out["scene"] == "Scene"
    assert out["view_layer"] == "ViewLayer"
    assert out["workspace"] == "Layout"
    assert out["context_mode"] == "OBJECT"
    assert out["object_mode"] == "OBJECT"
    assert out["active"]["name"] == "Cube"
    assert [obj["name"] for obj in out["selected"]] == ["Cube"]
    assert out["mesh_select_mode"] == {"vertex": True, "edge": False, "face": False}
    assert out["areas"]["has_view3d"] is True


def test_context_areas_reports_headless_empty_state(env):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "context.areas", {}, ctx)

    assert out == {"has_view3d": False, "windows": []}


def test_set_active_sets_active_and_optionally_selects(env):
    ctx, bpy = env
    reg = build_default_registry()
    sphere = bpy.data.objects.get("Sphere")

    out = dispatch_on_main(reg, "context.set_active", {"object": "Sphere"}, ctx)

    assert bpy.view_layer.objects.active is sphere
    assert sphere.select_get() is True
    assert out["active"]["name"] == "Sphere"


def test_set_active_rejects_hidden_or_unselectable_objects(env):
    ctx, bpy = env
    reg = build_default_registry()
    sphere = bpy.data.objects.get("Sphere")
    sphere.hide_select = True

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "context.set_active", {"object": "Sphere"}, ctx)
    assert exc.value.code == PRECONDITION

    sphere.hide_select = False
    sphere.hide_viewport = True
    with pytest.raises(BridgeError) as exc2:
        dispatch_on_main(reg, "context.set_active", {"object": "Sphere"}, ctx)
    assert exc2.value.code == PRECONDITION


def test_select_objects_replace_add_remove_toggle_and_active(env):
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "context.select_objects",
        {"objects": "Sphere", "action": "REPLACE", "active": "Sphere"},
        ctx,
    )
    assert [obj["name"] for obj in out["selected"]] == ["Sphere"]
    assert out["active"]["name"] == "Sphere"

    out = dispatch_on_main(reg, "context.select_objects", {"objects": "Cube", "action": "ADD"}, ctx)
    assert [obj["name"] for obj in out["selected"]] == ["Cube", "Sphere"]

    out = dispatch_on_main(reg, "context.select_objects", {"objects": "Sphere", "action": "REMOVE"}, ctx)
    assert [obj["name"] for obj in out["selected"]] == ["Cube"]

    out = dispatch_on_main(reg, "context.select_objects", {"objects": "Cube", "action": "TOGGLE"}, ctx)
    assert out["selected"] == []


def test_select_all_select_deselect_and_invert(env):
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "context.select_all", {"action": "SELECT"}, ctx)
    assert [obj["name"] for obj in out["selected"]] == ["Cube", "Sphere"]

    out = dispatch_on_main(reg, "context.select_all", {"action": "INVERT"}, ctx)
    assert out["selected"] == []

    out = dispatch_on_main(reg, "context.select_all", {"action": "DESELECT"}, ctx)
    assert out["selected"] == []


def test_mode_set_switches_mode_with_optional_object_activation(env):
    ctx, bpy = env
    reg = build_default_registry()
    sphere = bpy.data.objects.get("Sphere")

    out = dispatch_on_main(
        reg,
        "context.mode_set",
        {"mode": "EDIT", "object": "Sphere", "select": True},
        ctx,
    )

    assert bpy.view_layer.objects.active is sphere
    assert sphere.select_get() is True
    assert bpy.mode_calls == ["EDIT"]
    assert out["object_mode"] == "EDIT"
    assert out["active"]["name"] == "Sphere"


def test_mode_set_poll_and_runtime_failures_are_preconditions(env):
    ctx, bpy = env
    reg = build_default_registry()

    bpy.mode_poll_ok = False
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "context.mode_set", {"mode": "EDIT"}, ctx)
    assert exc.value.code == PRECONDITION

    bpy.mode_poll_ok = True
    bpy.mode_raise = True
    with pytest.raises(BridgeError) as exc2:
        dispatch_on_main(reg, "context.mode_set", {"mode": "EDIT"}, ctx)
    assert exc2.value.code == PRECONDITION


def test_mesh_select_mode_maps_named_modes(env):
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "context.mesh_select_mode", {"mode": "EDGE_FACE"}, ctx)

    assert bpy.tool_settings.mesh_select_mode == [False, True, True]
    assert out["mesh_select_mode"] == {"vertex": False, "edge": True, "face": True}
