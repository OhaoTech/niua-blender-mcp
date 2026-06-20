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
    ToolSpec(
        name="geometry_nodes.add_node",
        category="geometry_nodes",
        summary="Add a node to a Geometry Nodes modifier group",
        command="geometry_nodes.add_node",
        params={
            "object": Str(required=True, summary="Object owning the Geometry Nodes modifier"),
            "modifier": Str(default="", summary="Modifier name; defaults to first Geometry Nodes modifier"),
            "type": Str(required=True, summary="Node bl_idname, e.g. GeometryNodeTransform"),
            "name": Str(default="", summary="Optional node name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="geometry_nodes.link",
        category="geometry_nodes",
        summary="Create a link between two Geometry Nodes sockets",
        command="geometry_nodes.link",
        params={
            "object": Str(required=True, summary="Object owning the Geometry Nodes modifier"),
            "modifier": Str(default="", summary="Modifier name; defaults to first Geometry Nodes modifier"),
            "from_node": Str(required=True, summary="Source node name"),
            "from_socket": Str(required=True, summary="Source output socket name or index"),
            "to_node": Str(required=True, summary="Destination node name"),
            "to_socket": Str(required=True, summary="Destination input socket name or index"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
