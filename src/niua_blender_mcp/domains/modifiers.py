"""Modifiers domain manifest: the non-destructive modifier stack.

All modifier ops are object-mode: they act on a target object's ``modifiers``
collection. ``modifiers.add`` appends a new modifier of a supported type;
``modifiers.set`` writes a single property on an existing modifier;
``modifiers.apply``/``modifiers.remove`` bake or delete one; ``modifiers.list`` is a
read-only listing of the stack (the eyes). The kernel context resolver guarantees
OBJECT mode + the target active/selected before the apply/remove operators run, and
``check_poll`` surfaces a clean ``precondition_failed`` if Blender refuses (e.g.
applying a modifier on a multi-user mesh).
"""

from __future__ import annotations

from ..kernel import Bool, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="modifiers.types",
        category="modifiers",
        summary="List modifier types supported by the running Blender",
        command="modifiers.types",
        params={},
    ),
    ToolSpec(
        name="modifiers.add",
        category="modifiers",
        summary="Add a modifier to an object's stack",
        command="modifiers.add",
        params={
            "object": Str(summary="Object to modify (defaults to active)"),
            "type": Str(required=True, summary="Modifier type to add, e.g. SUBSURF or NODES"),
            "name": Str(summary="Name for the new modifier (defaults to the type label)"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="modifiers.set",
        category="modifiers",
        summary="Set a property on an existing modifier",
        command="modifiers.set",
        params={
            "object": Str(summary="Object owning the modifier (defaults to active)"),
            "name": Str(required=True, summary="Name of the modifier to edit"),
            "property": Str(required=True, summary="Modifier property to set (e.g. 'levels', 'thickness')"),
            "value": Str(required=True, summary="New value (coerced to the property's type)"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="modifiers.set_visibility",
        category="modifiers",
        summary="Set common modifier stack visibility flags",
        command="modifiers.set_visibility",
        params={
            "object": Str(summary="Object owning the modifier (defaults to active)"),
            "name": Str(required=True, summary="Name of the modifier to edit"),
            "viewport": Bool(summary="Show modifier in viewport"),
            "render": Bool(summary="Show modifier in renders"),
            "editmode": Bool(summary="Show modifier in edit mode"),
            "cage": Bool(summary="Show modifier on cage"),
            "expanded": Bool(summary="Show modifier panel expanded"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="modifiers.move",
        category="modifiers",
        summary="Move a modifier to a stack index",
        command="modifiers.move",
        params={
            "object": Str(summary="Object owning the modifier (defaults to active)"),
            "name": Str(required=True, summary="Name of the modifier to move"),
            "index": Int(required=True, minimum=0, summary="Destination stack index"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="modifiers.copy",
        category="modifiers",
        summary="Copy a modifier in the stack",
        command="modifiers.copy",
        params={
            "object": Str(summary="Object owning the modifier (defaults to active)"),
            "name": Str(required=True, summary="Name of the modifier to copy"),
            "new_name": Str(default="", summary="Optional name for the copied modifier"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="modifiers.apply",
        category="modifiers",
        summary="Apply (bake) a modifier into the mesh",
        command="modifiers.apply",
        params={
            "object": Str(summary="Object owning the modifier (defaults to active)"),
            "name": Str(required=True, summary="Name of the modifier to apply"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="modifiers.remove",
        category="modifiers",
        summary="Remove a modifier from the stack without applying it",
        command="modifiers.remove",
        params={
            "object": Str(summary="Object owning the modifier (defaults to active)"),
            "name": Str(required=True, summary="Name of the modifier to remove"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="modifiers.list",
        category="modifiers",
        summary="List the modifier stack of an object (read-only)",
        command="modifiers.list",
        params={
            "object": Str(summary="Object to inspect (defaults to active)"),
        },
    ),
]
