"""Topbar GUI-parity tool specs."""

from __future__ import annotations

from ..kernel import Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="topbar.report",
        category="topbar",
        summary="Report active topbar context, workspace, scene, and search capability",
        command="topbar.report",
    ),
    ToolSpec(
        name="topbar.command_search",
        category="topbar",
        summary="Search Blender commands exposed through bpy.ops without opening modal UI",
        command="topbar.command_search",
        params={
            "query": Str(default="", summary="Command search query"),
            "limit": Int(default=20, minimum=1, summary="Maximum results to return"),
        },
    ),
]
