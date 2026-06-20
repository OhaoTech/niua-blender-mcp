"""Context / selection / mode tool specs."""

from __future__ import annotations

from ..kernel import Bool, Enum, Str, ToolSpec

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
    ToolSpec(
        name="context.set_active",
        category="context",
        summary="Set the active object and optionally select it",
        command="context.set_active",
        params={
            "object": Str(required=True, summary="Object to make active"),
            "select": Bool(default=True, summary="Also select the object"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="context.select_objects",
        category="context",
        summary="Update object selection by comma-separated object names",
        command="context.select_objects",
        params={
            "objects": Str(required=True, summary="Comma-separated object names"),
            "action": Enum(["REPLACE", "ADD", "REMOVE", "TOGGLE"], default="REPLACE"),
            "active": Str(default="", summary="Optional active object after selection"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="context.select_all",
        category="context",
        summary="Select, deselect, or invert selection for all scene objects",
        command="context.select_all",
        params={"action": Enum(["SELECT", "DESELECT", "INVERT"], default="DESELECT")},
        mutates=True,
        feedback="viewport",
    ),
]
