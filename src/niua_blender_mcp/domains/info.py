"""Info editor GUI-parity tool specs."""

from __future__ import annotations

from ..kernel import Int, ToolSpec

SPECS = [
    ToolSpec(
        name="info.report",
        category="info",
        summary="Report Info editor areas and available report operators",
        command="info.report",
    ),
    ToolSpec(
        name="info.messages",
        category="info",
        summary="Return Info editor report messages when exposed by Blender RNA",
        command="info.messages",
        params={"limit": Int(default=100, minimum=0, summary="Maximum messages to return")},
    ),
]
