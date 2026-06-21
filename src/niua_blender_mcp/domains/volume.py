"""Volume GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec, Vec3

SPECS = [
    ToolSpec(
        name="volume.create_empty",
        category="volume",
        summary="Create an empty volume object",
        command="volume.create_empty",
        params={
            "name": Str(default="", summary="Optional object name"),
            "location": Vec3(default=[0, 0, 0], summary="World location"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="volume.import",
        category="volume",
        summary="Import an OpenVDB volume file",
        command="volume.import",
        params={
            "path": Str(required=True, summary="OpenVDB file path"),
            "name": Str(default="", summary="Optional object/data name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="volume.list",
        category="volume",
        summary="List volume objects and data-blocks",
        command="volume.list",
        params={},
    ),
    ToolSpec(
        name="volume.report",
        category="volume",
        summary="Report live RNA properties for a volume",
        command="volume.report",
        params={"name_or_object": Str(required=True, summary="Volume object or data-block name")},
    ),
    ToolSpec(
        name="volume.set",
        category="volume",
        summary="Set one writable RNA property on a volume data-block or nested settings object",
        command="volume.set",
        params={
            "name_or_object": Str(required=True, summary="Volume object or data-block name"),
            "property": Str(required=True, summary="Volume property path, e.g. filepath or display.density"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
