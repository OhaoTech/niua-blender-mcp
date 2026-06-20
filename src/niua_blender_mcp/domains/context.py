"""Context / selection / mode tool specs."""

from __future__ import annotations

from ..kernel import ToolSpec

SPECS = [
    ToolSpec(
        name="context.info",
        category="context",
        summary="Report active object, selected objects, mode, mesh select mode, and available areas",
        command="context.info",
    ),
    ToolSpec(
        name="context.areas",
        category="context",
        summary="List available editor areas for context overrides",
        command="context.areas",
    ),
]
