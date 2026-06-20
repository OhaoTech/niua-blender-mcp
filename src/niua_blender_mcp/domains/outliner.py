"""Scene tree / Outliner tool specs."""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

KINDS = ["AUTO", "ANY", "OBJECT", "COLLECTION", "SCENE", "VIEW_LAYER"]

SPECS = [
    ToolSpec(
        name="outliner.tree",
        category="outliner",
        summary="Return the logical scene tree: scenes, view layers, collections, objects, and hierarchy",
        command="outliner.tree",
    ),
    ToolSpec(
        name="outliner.describe",
        category="outliner",
        summary="Describe one object, collection, scene, or view layer by name",
        command="outliner.describe",
        params={
            "target": Str(required=True, summary="Name to describe"),
            "kind": Enum(["AUTO", "OBJECT", "COLLECTION", "SCENE", "VIEW_LAYER"], default="AUTO"),
        },
    ),
    ToolSpec(
        name="outliner.find",
        category="outliner",
        summary="Search objects, collections, scenes, and view layers by name",
        command="outliner.find",
        params={
            "query": Str(required=True, summary="Case-insensitive name substring"),
            "kind": Enum(KINDS, default="ANY", summary="Restrict result kind"),
            "limit": Int(default=50, minimum=1, maximum=500, summary="Maximum matches"),
        },
    ),
    ToolSpec(
        name="outliner.orphans",
        category="outliner",
        summary="List zero-user datablocks in high-value Outliner categories",
        command="outliner.orphans",
    ),
]
