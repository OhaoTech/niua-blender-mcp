"""UI automation / GUI parity tool specs."""

from __future__ import annotations

from ..kernel import Bool, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="ui.state",
        category="ui",
        summary="Report Blender UI availability, active window, and foreground-only capability flags",
        command="ui.state",
    ),
    ToolSpec(
        name="ui.windows",
        category="ui",
        summary="List Blender windows, screens, workspaces, areas, regions, and UI geometry",
        command="ui.windows",
    ),
    ToolSpec(
        name="ui.operator_poll",
        category="ui",
        summary="Check whether a Blender operator polls in an explicit editor area context",
        command="ui.operator_poll",
        params={
            "idname": Str(required=True, summary="Operator id, e.g. mesh.bevel"),
            "area": Str(default="VIEW_3D", summary="Editor area type used for temp_override"),
            "region": Str(default="WINDOW", summary="Region type inside the area"),
            "window_index": Int(default=-1, minimum=-1, summary="Specific window index, or -1 for first match"),
            "area_index": Int(default=-1, minimum=-1, summary="Specific area index, or -1 for first matching type"),
            "object": Str(summary="Optional active object name"),
            "mode": Str(summary="Optional interaction mode"),
            "select": Str(summary="Selected object names as a JSON array string"),
            "require_area": Bool(default=False, summary="Return unavailable if the target UI area is missing"),
        },
    ),
    ToolSpec(
        name="ui.operator_invoke",
        category="ui",
        summary="Run any Blender operator with explicit editor area context and undo-safe dispatch",
        command="ui.operator_invoke",
        params={
            "idname": Str(required=True, summary="Operator id, e.g. mesh.bevel"),
            "args": Str(summary="Operator arguments as a JSON object string"),
            "area": Str(default="VIEW_3D", summary="Editor area type used for temp_override"),
            "region": Str(default="WINDOW", summary="Region type inside the area"),
            "window_index": Int(default=-1, minimum=-1, summary="Specific window index, or -1 for first match"),
            "area_index": Int(default=-1, minimum=-1, summary="Specific area index, or -1 for first matching type"),
            "object": Str(summary="Optional active object name"),
            "mode": Str(summary="Optional interaction mode"),
            "select": Str(summary="Selected object names as a JSON array string"),
            "require_area": Bool(default=False, summary="Fail if the target UI area is missing"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="ui.screenshot",
        category="ui",
        summary="Capture Blender's UI screenshot when screen.screenshot is available",
        command="ui.screenshot",
        params={
            "path": Str(required=True, summary="Output screenshot path"),
            "full": Bool(default=False, summary="Capture the full Blender window when supported"),
        },
    ),
    ToolSpec(
        name="ui.redraw",
        category="ui",
        summary="Request a Blender UI redraw when wm.redraw_timer is available",
        command="ui.redraw",
        params={
            "type": Str(default="DRAW_WIN_SWAP", summary="Redraw timer type"),
            "iterations": Int(default=1, minimum=1, summary="Number of redraw iterations"),
        },
    ),
]
