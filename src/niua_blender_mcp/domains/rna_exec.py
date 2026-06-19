"""Generic RNA execution domain: the long-tail escape hatch.

``rna.describe`` lets the agent *discover* any operator or type; this domain lets the
agent *execute* anything it discovered without us hand-writing a ToolSpec for it.

Three tools, all routed through the same validate -> ctx.ensure -> undo pipeline as
curated tools:

- ``rna.call_operator`` — run any ``bpy.ops.<cat>.<name>`` operator. Args are validated
  and coerced against the operator's own ``get_rna_type().properties`` (unknown keys
  dropped, numbers/enums coerced, POINTER/COLLECTION props ignored with a note).
- ``rna.set_property`` — resolve a dotted path under ``bpy.data`` and assign a value.
- ``rna.get_property`` — read a dotted path under ``bpy.data``.

Args-passing approach: kernel params have no free-form object/array-of-string kind yet,
so ``args`` / ``value`` are accepted as **JSON-encoded strings** (Str params) and parsed
with ``json.loads`` in the handler. This keeps the kernel contract untouched (no new
param kind, all existing contract tests stay green). The MCP descriptions tell the agent
to pass a JSON object/array/scalar encoded as a string.
"""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="rna.call_operator",
        category="rna_exec",
        summary="Run any bpy.ops operator, with args validated against its RNA",
        command="rna.call_operator",
        params={
            "idname": Str(
                required=True,
                summary="Operator id, e.g. 'mesh.bevel' or 'object.shade_smooth'",
            ),
            "args": Str(
                summary="Operator arguments as a JSON object string, e.g. '{\"offset\": 0.2}'",
            ),
            "object": Str(summary="Active object name to set before running (optional)"),
            "mode": Str(summary="Interaction mode, e.g. 'EDIT' / 'OBJECT' (optional)"),
            "select": Str(
                summary="Object names to select as a JSON array string, e.g. '[\"Cube\"]'",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="rna.set_property",
        category="rna_exec",
        summary="Set a data property by path under bpy.data (value is JSON-encoded)",
        command="rna.set_property",
        params={
            "path": Str(
                required=True,
                summary="Dotted path under bpy.data, e.g. 'objects.Cube.location'",
            ),
            "value": Str(
                required=True,
                summary="New value as a JSON string, e.g. '[1, 2, 3]' or '0.5' or '\"NAME\"'",
            ),
        },
        mutates=True,
    ),
    ToolSpec(
        name="rna.get_property",
        category="rna_exec",
        summary="Read a data property by path under bpy.data (read-only)",
        command="rna.get_property",
        params={
            "path": Str(
                required=True,
                summary="Dotted path under bpy.data, e.g. 'objects.Cube.location'",
            ),
        },
    ),
]
