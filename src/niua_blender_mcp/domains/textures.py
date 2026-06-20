"""Texture/image datablock tools used by shader materials."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="textures.load",
        category="textures",
        summary="Load an image datablock from disk",
        command="textures.load",
        params={
            "path": Str(required=True, summary="Filesystem path to the image"),
            "name": Str(default="", summary="Optional image datablock name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="textures.list",
        category="textures",
        summary="List image datablocks",
        command="textures.list",
        params={},
    ),
    ToolSpec(
        name="textures.report",
        category="textures",
        summary="Report one image datablock",
        command="textures.report",
        params={"name": Str(required=True, summary="Image datablock name")},
    ),
]
