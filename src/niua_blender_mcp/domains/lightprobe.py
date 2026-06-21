"""Light probe GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Enum, Str, ToolSpec, Vec3

LIGHTPROBE_TYPES = ["SPHERE", "PLANE", "VOLUME"]

SPECS = [
    ToolSpec(
        name="lightprobe.create",
        category="lightprobe",
        summary="Create a light probe object",
        command="lightprobe.create",
        params={
            "type": Enum(LIGHTPROBE_TYPES, required=True, summary="Light probe type"),
            "name": Str(default="", summary="Optional object name"),
            "location": Vec3(default=[0, 0, 0], summary="World location"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="lightprobe.list",
        category="lightprobe",
        summary="List light probe objects",
        command="lightprobe.list",
        params={},
    ),
    ToolSpec(
        name="lightprobe.report",
        category="lightprobe",
        summary="Report live RNA properties for a light probe",
        command="lightprobe.report",
        params={"name": Str(required=True, summary="Light probe object name")},
    ),
    ToolSpec(
        name="lightprobe.set",
        category="lightprobe",
        summary="Set one RNA property on a light probe data-block",
        command="lightprobe.set",
        params={
            "name": Str(required=True, summary="Light probe object name"),
            "property": Str(required=True, summary="Light probe data property"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
