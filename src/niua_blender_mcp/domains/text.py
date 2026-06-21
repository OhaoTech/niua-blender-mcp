"""Text Editor GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="text.list",
        category="text",
        summary="List Text data-blocks",
        command="text.list",
        params={},
    ),
    ToolSpec(
        name="text.create",
        category="text",
        summary="Create a Text data-block",
        command="text.create",
        params={
            "name": Str(required=True, summary="Text data-block name"),
            "body": Str(default="", summary="Initial text body"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="text.open",
        category="text",
        summary="Open a text file into a Text data-block",
        command="text.open",
        params={
            "path": Str(required=True, summary="Text file path"),
            "name": Str(default="", summary="Optional data-block name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="text.read",
        category="text",
        summary="Read a Text data-block",
        command="text.read",
        params={"name": Str(required=True, summary="Text data-block name")},
    ),
    ToolSpec(
        name="text.write",
        category="text",
        summary="Replace a Text data-block body",
        command="text.write",
        params={
            "name": Str(required=True, summary="Text data-block name"),
            "body": Str(required=True, summary="New text body"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="text.append",
        category="text",
        summary="Append to a Text data-block body",
        command="text.append",
        params={
            "name": Str(required=True, summary="Text data-block name"),
            "body": Str(required=True, summary="Text to append"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="text.save",
        category="text",
        summary="Save a Text data-block to disk",
        command="text.save",
        params={
            "name": Str(required=True, summary="Text data-block name"),
            "path": Str(default="", summary="Optional save path; defaults to text.filepath"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="text.remove",
        category="text",
        summary="Remove a Text data-block",
        command="text.remove",
        params={"name": Str(required=True, summary="Text data-block name")},
        mutates=True,
        feedback="viewport",
    ),
]
