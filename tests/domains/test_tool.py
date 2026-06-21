"""Tool settings GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import PRECONDITION, BridgeError


class FakeEnumItem:
    def __init__(self, identifier: str, name: str = "") -> None:
        self.identifier = identifier
        self.name = name or identifier.title()


class FakeRnaProp:
    def __init__(
        self,
        identifier: str,
        type: str,
        *,
        is_readonly: bool = False,
        enum_items: list[FakeEnumItem] | None = None,
    ) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = False
        self.array_length = 0
        self.enum_items = list(enum_items or [])
        self.enum_items_static = list(enum_items or [])


class FakeRnaProperties(list):
    def get(self, identifier: str):
        return next((prop for prop in self if prop.identifier == identifier), None)

    def __getitem__(self, key):
        if isinstance(key, str):
            prop = self.get(key)
            if prop is None:
                raise KeyError(key)
            return prop
        return super().__getitem__(key)


def _rna(*props: FakeRnaProp):
    return types.SimpleNamespace(properties=FakeRnaProperties([FakeRnaProp("rna_type", "POINTER", is_readonly=True), *props]))


class FakeParticleEditSettings:
    def __init__(self) -> None:
        self.use_emitter_deflect = False
        self.bl_rna = _rna(FakeRnaProp("use_emitter_deflect", "BOOLEAN"))


class FakeToolSettings:
    def __init__(self) -> None:
        self.workspace_tool_type = "DEFAULT"
        self.use_snap = False
        self.double_threshold = 0.001
        self.transform_pivot_point = "MEDIAN_POINT"
        self.read_only_value = "locked"
        self.particle_edit = FakeParticleEditSettings()
        self.bl_rna = _rna(
            FakeRnaProp(
                "workspace_tool_type",
                "ENUM",
                enum_items=[FakeEnumItem("DEFAULT"), FakeEnumItem("FALLBACK")],
            ),
            FakeRnaProp("use_snap", "BOOLEAN"),
            FakeRnaProp("double_threshold", "FLOAT"),
            FakeRnaProp(
                "transform_pivot_point",
                "ENUM",
                enum_items=[FakeEnumItem("MEDIAN_POINT"), FakeEnumItem("CURSOR")],
            ),
            FakeRnaProp("read_only_value", "STRING", is_readonly=True),
            FakeRnaProp("particle_edit", "POINTER", is_readonly=True),
        )


class FakeTool:
    def __init__(self, idname: str = "", *, space_type: str = "VIEW_3D", mode: str = "OBJECT", index: int = 0) -> None:
        self.idname = idname
        self.idname_fallback = ""
        self.index = index
        self.space_type = space_type
        self.mode = mode
        self.has_datablock = False
        self.use_brushes = False
        self.brush_type = "ANY"
        self.widget = ""
        self.refresh_count = 0
        self.bl_rna = _rna(
            FakeRnaProp("idname", "STRING"),
            FakeRnaProp("idname_fallback", "STRING"),
            FakeRnaProp("index", "INT", is_readonly=True),
            FakeRnaProp("space_type", "ENUM", is_readonly=True),
            FakeRnaProp("mode", "ENUM", is_readonly=True),
            FakeRnaProp("has_datablock", "BOOLEAN", is_readonly=True),
            FakeRnaProp("use_brushes", "BOOLEAN", is_readonly=True),
            FakeRnaProp("brush_type", "ENUM", is_readonly=True),
            FakeRnaProp("widget", "STRING", is_readonly=True),
        )

    def refresh_from_context(self):
        self.refresh_count += 1


class FakeWorkspaceTools:
    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], FakeTool] = {}

    def from_space_view3d_mode(self, mode: str, create: bool = False):
        return self._get("VIEW_3D", mode, create)

    def from_space_image_mode(self, mode: str, create: bool = False):
        return self._get("IMAGE_EDITOR", mode, create)

    def from_space_node(self, create: bool = False):
        return self._get("NODE_EDITOR", "DEFAULT", create)

    def from_space_sequencer(self, mode: str, create: bool = False):
        return self._get("SEQUENCE_EDITOR", mode, create)

    def _get(self, area_type: str, mode: str, create: bool):
        key = (area_type, mode)
        if key not in self._tools and create:
            self._tools[key] = FakeTool(space_type=area_type, mode=mode)
        return self._tools.get(key)


class FakeObject:
    def __init__(self, name: str) -> None:
        self.name = name
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.op_calls: list = []
        self.mode_calls: list[str] = []
        self.undo_pushes: list[str] = []
        self.object = FakeObject("Cube")
        self.scene = types.SimpleNamespace(objects=[self.object])
        self.workspace = types.SimpleNamespace(name="Layout", tools=FakeWorkspaceTools())
        self.workspace.tools.from_space_view3d_mode("OBJECT", create=True).idname = "builtin.select_box"
        self.tool_settings = FakeToolSettings()
        self.supported_tools = {"builtin.select_box": 1, "builtin.move": 0}

        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy.object

            @active.setter
            def active(self_inner, value):
                bpy.object = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        class _Context:
            scene = self.scene
            workspace = self.workspace
            tool_settings = self.tool_settings
            view_layer = self.view_layer
            mode = "OBJECT"
            space_data = types.SimpleNamespace(type="VIEW_3D", mode="VIEW", view_type="SEQUENCER")
            window_manager = types.SimpleNamespace(windows=[])

            @property
            def object(self_inner):
                return bpy.object

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()

        class _WmOps:
            @staticmethod
            def tool_set_by_id(name: str = "", space_type: str = "EMPTY", **kwargs):
                bpy.op_calls.append(("wm.tool_set_by_id", {"name": name, "space_type": space_type, **kwargs}))
                if name not in bpy.supported_tools:
                    return {"CANCELLED"}
                tool = bpy.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=True)
                tool.idname = name
                tool.index = bpy.supported_tools[name]
                return {"FINISHED"}

            @staticmethod
            def redraw_timer(**kwargs):
                bpy.op_calls.append(("wm.redraw_timer", kwargs))

        class _ObjectOps:
            @staticmethod
            def mode_set(mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                bpy.object.mode = mode
                bpy.context.mode = mode

        class _EdOps:
            @staticmethod
            def undo_push(message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(wm=_WmOps(), object=_ObjectOps(), ed=_EdOps())

    @property
    def data(self):
        return types.SimpleNamespace(objects=types.SimpleNamespace(get=lambda name: self.object if name == self.object.name else None))


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_tool_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "tool.active",
        "tool.set",
        "tool.settings",
        "tool.setting_get",
        "tool.setting_set",
    } <= names


def test_active_reports_workspace_tool(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    result = dispatch_on_main(reg, "tool.active", {"area_type": "VIEW_3D", "mode": "OBJECT"}, ctx)

    assert result["available"] is True
    assert result["workspace"] == "Layout"
    assert result["active_tool"]["idname"] == "builtin.select_box"
    assert result["active_tool"]["space_type"] == "VIEW_3D"
    assert result["active_tool"]["mode"] == "OBJECT"


def test_set_switches_workspace_tool_with_operator_and_undo(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    result = dispatch_on_main(reg, "tool.set", {"idname": "builtin.move", "area_type": "VIEW_3D", "mode": "OBJECT"}, ctx)

    assert result["available"] is True
    assert result["active_tool"]["idname"] == "builtin.move"
    assert ("wm.tool_set_by_id", {"name": "builtin.move", "space_type": "VIEW_3D"}) in bpy.op_calls
    assert bpy.undo_pushes == ["niua:tool.set"]


def test_settings_reports_active_tool_and_tool_settings_rna(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    result = dispatch_on_main(reg, "tool.settings", {"area_type": "VIEW_3D", "mode": "OBJECT"}, ctx)

    props = result["tool_settings"]["properties"]
    assert result["active_tool"]["idname"] == "builtin.select_box"
    assert props["use_snap"]["value"] is False
    assert props["transform_pivot_point"]["enum_items"][0]["identifier"] == "MEDIAN_POINT"
    assert "rna_type" not in props


def test_setting_get_and_set_support_json_values_and_nested_paths(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    before = dispatch_on_main(reg, "tool.setting_get", {"path": "use_snap"}, ctx)
    assert before["value"] is False

    snap = dispatch_on_main(reg, "tool.setting_set", {"path": "use_snap", "value": "true"}, ctx)
    assert snap["value"] is True
    assert bpy.tool_settings.use_snap is True

    threshold = dispatch_on_main(reg, "tool.setting_set", {"path": "double_threshold", "value": "0.25"}, ctx)
    assert threshold["value"] == 0.25
    assert bpy.tool_settings.double_threshold == 0.25

    nested = dispatch_on_main(
        reg,
        "tool.setting_set",
        {"path": "particle_edit.use_emitter_deflect", "value": json.dumps(True)},
        ctx,
    )
    assert nested["value"] is True
    assert bpy.tool_settings.particle_edit.use_emitter_deflect is True


def test_cancelled_tool_set_fails_without_undo(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "tool.set", {"idname": "builtin.nope", "area_type": "VIEW_3D"}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_read_only_tool_setting_fails_without_undo(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "tool.setting_set", {"path": "read_only_value", "value": json.dumps("open")}, ctx)

    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []
