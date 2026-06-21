"""Tool settings GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="tool.active",
        category="tool",
        summary="Report the active workspace tool for an editor/mode",
        command="tool.active",
        params={
            "area_type": Str(default="VIEW_3D", summary="Editor area type, e.g. VIEW_3D"),
            "mode": Str(default="", summary="Optional mode, e.g. OBJECT or EDIT_MESH"),
        },
    ),
    ToolSpec(
        name="tool.set",
        category="tool",
        summary="Switch the active workspace tool by idname",
        command="tool.set",
        params={
            "idname": Str(required=True, summary="Tool idname, e.g. builtin.move"),
            "area_type": Str(default="VIEW_3D", summary="Editor area type, e.g. VIEW_3D"),
            "mode": Str(default="", summary="Optional mode, e.g. OBJECT or EDIT_MESH"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="tool.settings",
        category="tool",
        summary="Report active tool and live ToolSettings RNA properties",
        command="tool.settings",
        params={
            "area_type": Str(default="VIEW_3D", summary="Editor area type, e.g. VIEW_3D"),
            "mode": Str(default="", summary="Optional mode, e.g. OBJECT or EDIT_MESH"),
        },
    ),
    ToolSpec(
        name="tool.setting_get",
        category="tool",
        summary="Read one ToolSettings path",
        command="tool.setting_get",
        params={"path": Str(required=True, summary="Dot path under bpy.context.tool_settings")},
    ),
    ToolSpec(
        name="tool.setting_set",
        category="tool",
        summary="Set one ToolSettings path",
        command="tool.setting_set",
        params={
            "path": Str(required=True, summary="Dot path under bpy.context.tool_settings"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
