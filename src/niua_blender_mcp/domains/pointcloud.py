"""Point cloud GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="pointcloud.list",
        category="pointcloud",
        summary="List point cloud objects and data-blocks",
        command="pointcloud.list",
        params={},
    ),
    ToolSpec(
        name="pointcloud.report",
        category="pointcloud",
        summary="Report live RNA properties for a point cloud",
        command="pointcloud.report",
        params={"name_or_object": Str(required=True, summary="Point cloud object or data-block name")},
    ),
    ToolSpec(
        name="pointcloud.set",
        category="pointcloud",
        summary="Set one writable RNA property on a point cloud data-block",
        command="pointcloud.set",
        params={
            "name_or_object": Str(required=True, summary="Point cloud object or data-block name"),
            "property": Str(required=True, summary="PointCloud data property"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="pointcloud.attributes",
        category="pointcloud",
        summary="List point cloud geometry attributes and color attributes",
        command="pointcloud.attributes",
        params={"name_or_object": Str(required=True, summary="Point cloud object or data-block name")},
    ),
]
