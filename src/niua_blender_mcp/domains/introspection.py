"""Introspection domain manifest: live RNA discovery for the agent."""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="rna.describe",
        category="introspection",
        summary="Describe a Blender operator or type via RNA (e.g. 'op:mesh.bevel', 'type:Object')",
        command="rna.describe",
        params={"path": Str(required=True, summary="'op:<cat>.<name>' or 'type:<TypeName>'")},
    ),
    ToolSpec(
        name="rna.search",
        category="introspection",
        summary="Search the live Blender API for operators/types matching a query, ranked by relevance",
        command="rna.search",
        params={
            "query": Str(
                required=True,
                summary="Substring to match against idname/label/description (e.g. 'bevel', 'subdivide')",
            ),
            "kind": Enum(
                ["operator", "type", "any"],
                default="any",
                summary="Restrict results to operators, types, or both",
            ),
            "category": Str(
                summary="Optional operator category to scope to (e.g. 'mesh', 'object')",
            ),
            "limit": Int(default=30, minimum=1, summary="Max number of matches to return"),
        },
    ),
]
