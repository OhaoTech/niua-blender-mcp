"""Constraints GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Enum, Str, ToolSpec

_OWNER = Enum(["OBJECT", "BONE"], default="OBJECT", summary="Constraint owner stack")

SPECS = [
    ToolSpec(
        name="constraints.list",
        category="constraints",
        summary="List object or pose-bone constraints",
        command="constraints.list",
        params={
            "object": Str(required=True, summary="Object owning the constraint stack"),
            "owner": _OWNER,
            "bone": Str(default="", summary="Pose bone name when owner is BONE"),
        },
    ),
    ToolSpec(
        name="constraints.add",
        category="constraints",
        summary="Add an object or pose-bone constraint",
        command="constraints.add",
        params={
            "object": Str(required=True, summary="Object owning the constraint stack"),
            "type": Str(required=True, summary="Blender constraint type, e.g. COPY_LOCATION or IK"),
            "name": Str(default="", summary="Optional constraint name"),
            "owner": _OWNER,
            "bone": Str(default="", summary="Pose bone name when owner is BONE"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="constraints.remove",
        category="constraints",
        summary="Remove a named object or pose-bone constraint",
        command="constraints.remove",
        params={
            "object": Str(required=True, summary="Object owning the constraint stack"),
            "name": Str(required=True, summary="Constraint name to remove"),
            "owner": _OWNER,
            "bone": Str(default="", summary="Pose bone name when owner is BONE"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="constraints.report",
        category="constraints",
        summary="Report live RNA properties for object or pose-bone constraints",
        command="constraints.report",
        params={
            "object": Str(required=True, summary="Object owning the constraint stack"),
            "name": Str(default="", summary="Optional constraint name; omit for all"),
            "owner": _OWNER,
            "bone": Str(default="", summary="Pose bone name when owner is BONE"),
        },
    ),
    ToolSpec(
        name="constraints.set",
        category="constraints",
        summary="Set one RNA property on an object or pose-bone constraint",
        command="constraints.set",
        params={
            "object": Str(required=True, summary="Object owning the constraint stack"),
            "name": Str(required=True, summary="Constraint name to edit"),
            "property": Str(required=True, summary="Constraint RNA property identifier"),
            "value": Str(required=True, summary="New value as JSON, e.g. 0.5, false, or {\"object\":\"Cube\"}"),
            "owner": _OWNER,
            "bone": Str(default="", summary="Pose bone name when owner is BONE"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
