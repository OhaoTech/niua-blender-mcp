"""Geometry Nodes domain manifest: create and inspect node modifiers."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="geometry_nodes.create_modifier",
        category="geometry_nodes",
        summary="Create a Geometry Nodes modifier with Blender's default node group",
        command="geometry_nodes.create_modifier",
        params={
            "object": Str(required=True, summary="Object receiving the Geometry Nodes modifier"),
            "name": Str(default="", summary="Optional modifier name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="geometry_nodes.report",
        category="geometry_nodes",
        summary="Report a Geometry Nodes modifier and its node group",
        command="geometry_nodes.report",
        params={
            "object": Str(required=True, summary="Object owning the Geometry Nodes modifier"),
            "modifier": Str(default="", summary="Modifier name; defaults to first Geometry Nodes modifier"),
        },
    ),
]
