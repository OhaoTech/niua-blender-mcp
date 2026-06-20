"""UI automation / GUI parity tool specs."""

from __future__ import annotations

from ..kernel import ToolSpec

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
]
