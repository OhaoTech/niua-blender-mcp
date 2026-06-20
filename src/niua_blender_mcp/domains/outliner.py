"""Scene tree / Outliner tool specs."""

from __future__ import annotations

from ..kernel import Bool, Enum, Int, Str, ToolSpec

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
    ToolSpec(
        name="outliner.collection_create",
        category="outliner",
        summary="Create a collection under the scene root or a named parent collection",
        command="outliner.collection_create",
        params={
            "name": Str(required=True, summary="New collection name"),
            "parent": Str(default="", summary="Parent collection; scene root when empty"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.collection_rename",
        category="outliner",
        summary="Rename a collection",
        command="outliner.collection_rename",
        params={
            "collection": Str(required=True, summary="Collection to rename"),
            "name": Str(required=True, summary="New collection name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.collection_delete",
        category="outliner",
        summary="Delete a collection; force is required when it contains objects or child collections",
        command="outliner.collection_delete",
        params={
            "collection": Str(required=True, summary="Collection to delete"),
            "force": Bool(default=False, summary="Allow deleting a non-empty collection"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.object_link",
        category="outliner",
        summary="Link an object into a collection without removing existing collection membership",
        command="outliner.object_link",
        params={
            "object": Str(required=True, summary="Object to link"),
            "collection": Str(required=True, summary="Target collection"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.object_unlink",
        category="outliner",
        summary="Unlink an object from a collection; force is required if it is the final collection",
        command="outliner.object_unlink",
        params={
            "object": Str(required=True, summary="Object to unlink"),
            "collection": Str(required=True, summary="Collection to unlink from"),
            "force": Bool(default=False, summary="Allow object to have no collection users"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.object_move",
        category="outliner",
        summary="Move an object to exactly one target collection",
        command="outliner.object_move",
        params={
            "object": Str(required=True, summary="Object to move"),
            "collection": Str(required=True, summary="Target collection"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.parent_set",
        category="outliner",
        summary="Set an object's parent, preserving world transform by default",
        command="outliner.parent_set",
        params={
            "object": Str(required=True, summary="Child object"),
            "parent": Str(required=True, summary="Parent object"),
            "keep_transform": Bool(default=True, summary="Preserve world transform"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.parent_clear",
        category="outliner",
        summary="Clear an object's parent, preserving world transform by default",
        command="outliner.parent_clear",
        params={
            "object": Str(required=True, summary="Object to unparent"),
            "keep_transform": Bool(default=True, summary="Preserve world transform"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.visibility_set",
        category="outliner",
        summary="Set object-level viewport/render/selectability restrictions",
        command="outliner.visibility_set",
        params={
            "object": Str(required=True, summary="Object to update"),
            "viewport": Bool(summary="Visible in viewport"),
            "render": Bool(summary="Renderable"),
            "selectable": Bool(summary="Selectable"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="outliner.collection_visibility_set",
        category="outliner",
        summary="Set collection-level viewport/render/selectability restrictions",
        command="outliner.collection_visibility_set",
        params={
            "collection": Str(required=True, summary="Collection to update"),
            "viewport": Bool(summary="Visible in viewport"),
            "render": Bool(summary="Renderable"),
            "selectable": Bool(summary="Selectable"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
