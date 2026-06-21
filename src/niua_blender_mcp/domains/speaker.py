"""Speaker GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec, Vec3

SPECS = [
    ToolSpec(
        name="speaker.create",
        category="speaker",
        summary="Create a speaker object",
        command="speaker.create",
        params={
            "name": Str(default="", summary="Optional object name"),
            "location": Vec3(default=[0, 0, 0], summary="World location"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="speaker.list",
        category="speaker",
        summary="List speaker objects",
        command="speaker.list",
        params={},
    ),
    ToolSpec(
        name="speaker.report",
        category="speaker",
        summary="Report live RNA properties for a speaker",
        command="speaker.report",
        params={"name": Str(required=True, summary="Speaker object name")},
    ),
    ToolSpec(
        name="speaker.set",
        category="speaker",
        summary="Set one writable RNA property on a speaker data-block",
        command="speaker.set",
        params={
            "name": Str(required=True, summary="Speaker object name"),
            "property": Str(required=True, summary="Speaker data property"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
