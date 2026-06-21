"""Physics GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Enum, Str, ToolSpec

_PHYSICS_TYPE = Enum(
    ["RIGID_BODY", "RIGID_BODY_CONSTRAINT", "CLOTH", "SOFT_BODY", "FLUID", "DYNAMIC_PAINT", "FIELD"],
    required=True,
    summary="Physics stack type",
)

SPECS = [
    ToolSpec(
        name="physics.report",
        category="physics",
        summary="Report all physics stacks on an object",
        command="physics.report",
        params={"object": Str(required=True, summary="Object to inspect")},
    ),
    ToolSpec(
        name="physics.add",
        category="physics",
        summary="Add a physics stack to an object",
        command="physics.add",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "type": _PHYSICS_TYPE,
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="physics.remove",
        category="physics",
        summary="Remove a physics stack from an object",
        command="physics.remove",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "type": _PHYSICS_TYPE,
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="physics.set",
        category="physics",
        summary="Set one RNA property on a physics stack",
        command="physics.set",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "type": _PHYSICS_TYPE,
            "property": Str(required=True, summary="RNA property path, e.g. mass or settings.quality"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="physics.field_report",
        category="physics",
        summary="Report an object's force field settings",
        command="physics.field_report",
        params={"object": Str(required=True, summary="Object to inspect")},
    ),
    ToolSpec(
        name="physics.field_set",
        category="physics",
        summary="Set one RNA property on an object's force field",
        command="physics.field_set",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "property": Str(required=True, summary="Force field RNA property identifier"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
