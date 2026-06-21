"""Properties editor / RNA completeness domain.

This is the reflection floor for Blender's Properties editor data. Curated domains
remain nicer for common workflows, but these tools expose object and mesh data-block
properties without hard-coded panel lists.
"""

from __future__ import annotations

from ..kernel import Bool, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="properties.report",
        category="properties",
        summary="Report all live RNA properties for any stable Properties path target",
        command="properties.report",
        params={
            "path": Str(required=True, summary="Stable root path, e.g. object:Cube or data:meshes/CubeMesh"),
            "include_values": Bool(default=True, summary="Include current property values when readable"),
        },
    ),
    ToolSpec(
        name="properties.object_report",
        category="properties",
        summary="Report all live RNA properties for an object, its data, modifiers, and custom props",
        command="properties.object_report",
        params={
            "object": Str(required=True, summary="Object name"),
            "include_data": Bool(default=True, summary="Include object.data RNA properties"),
            "include_modifiers": Bool(default=True, summary="Include modifier RNA properties"),
            "include_values": Bool(default=True, summary="Include current property values when readable"),
        },
    ),
    ToolSpec(
        name="properties.get",
        category="properties",
        summary="Read a stable Properties path such as object:Cube/location or object:Cube/idprops/foo",
        command="properties.get",
        params={"path": Str(required=True, summary="Stable path, with path segments percent-encoded if needed")},
    ),
    ToolSpec(
        name="properties.set",
        category="properties",
        summary="Set a stable Properties path; value is JSON-encoded",
        command="properties.set",
        params={
            "path": Str(required=True, summary="Stable path to a mutable RNA or custom property"),
            "value": Str(required=True, summary="New value as a JSON string"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="properties.unset",
        category="properties",
        summary="Unset a custom property or resettable RNA property by stable Properties path",
        command="properties.unset",
        params={"path": Str(required=True, summary="Stable path to remove or reset")},
        mutates=True,
        feedback="viewport",
    ),
]
