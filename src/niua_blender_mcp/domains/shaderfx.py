"""Shader effects GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="shaderfx.list",
        category="shaderfx",
        summary="List shader effects on a Grease Pencil object",
        command="shaderfx.list",
        params={"object": Str(required=True, summary="Object to inspect")},
    ),
    ToolSpec(
        name="shaderfx.types",
        category="shaderfx",
        summary="List shader effect types supported by the running Blender",
        command="shaderfx.types",
        params={},
    ),
    ToolSpec(
        name="shaderfx.add",
        category="shaderfx",
        summary="Add a shader effect to a Grease Pencil object's stack",
        command="shaderfx.add",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "type": Str(required=True, summary="Shader effect type, e.g. FX_BLUR"),
            "name": Str(default="", summary="Optional shader effect name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shaderfx.remove",
        category="shaderfx",
        summary="Remove a named shader effect",
        command="shaderfx.remove",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "name": Str(required=True, summary="Shader effect name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shaderfx.report",
        category="shaderfx",
        summary="Report live RNA properties for one or all shader effects",
        command="shaderfx.report",
        params={
            "object": Str(required=True, summary="Object to inspect"),
            "name": Str(default="", summary="Optional shader effect name; omit for all"),
        },
    ),
    ToolSpec(
        name="shaderfx.set",
        category="shaderfx",
        summary="Set one RNA property on a shader effect",
        command="shaderfx.set",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "name": Str(required=True, summary="Shader effect name"),
            "property": Str(required=True, summary="Shader effect RNA property identifier"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
