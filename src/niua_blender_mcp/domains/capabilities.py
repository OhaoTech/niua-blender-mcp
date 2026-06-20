"""capabilities meta-domain (server side): the discoverability front door.

Mirrors blender_addon/.../domains/capabilities.py COMMANDS by name (parity test).
search/describe/invoke supersede the rna.* tools (kept as aliases); the agent is
told to start here.
"""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="capabilities.domains",
        category="capabilities",
        summary="List the craft domains and how many operations each exposes",
        command="capabilities.domains",
        tier="reflection",
    ),
    ToolSpec(
        name="capabilities.search",
        category="capabilities",
        summary="Search ALL of Blender for a capability by keyword, ranked (start here)",
        command="capabilities.search",
        params={
            "query": Str(required=True, summary="What you want to do, e.g. 'bevel', 'unwrap', 'smooth'"),
            "kind": Enum(["operator", "type", "any"], default="any", summary="Restrict to operators, types, or both"),
            "domain": Str(summary="Optional craft domain/category to scope to, e.g. 'mesh', 'uv'"),
            "limit": Int(default=30, minimum=1, summary="Max matches"),
        },
        tier="reflection",
    ),
    ToolSpec(
        name="capabilities.describe",
        category="capabilities",
        summary="Get the full typed parameter schema for one operation before calling it",
        command="capabilities.describe",
        params={"id": Str(required=True, summary="Operator id, e.g. 'mesh.bevel'")},
        tier="reflection",
    ),
    ToolSpec(
        name="capabilities.invoke",
        category="capabilities",
        summary="Run any Blender operator with args validated against its schema (undo-safe)",
        command="capabilities.invoke",
        params={
            "idname": Str(required=True, summary="Operator id, e.g. 'mesh.bevel'"),
            "args": Str(summary="Args as a JSON object string, e.g. '{\"offset\": 0.2}'"),
            "object": Str(summary="Active object name to set before running (optional)"),
            "mode": Str(summary="Interaction mode, e.g. 'EDIT' / 'OBJECT' (optional)"),
            "select": Str(summary="Object names to select as a JSON array string, e.g. '[\"Cube\"]'"),
        },
        mutates=True,
        feedback="viewport",
        tier="reflection",
    ),
]
