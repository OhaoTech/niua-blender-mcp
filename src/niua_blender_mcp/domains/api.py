"""API editor/source GUI-parity tool specs."""

from __future__ import annotations

from ..kernel import Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="api.report",
        category="api",
        summary="Report live Blender API operator/type metadata surface",
        command="api.report",
    ),
    ToolSpec(
        name="api.search",
        category="api",
        summary="Search live Blender API operators and RNA types",
        command="api.search",
        params={
            "query": Str(default="", summary="Search query"),
            "limit": Int(default=20, minimum=1, summary="Maximum results to return"),
        },
    ),
]
