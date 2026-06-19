"""Introspection domain manifest: live RNA discovery for the agent."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="rna.describe",
        category="introspection",
        summary="Describe a Blender operator or type via RNA (e.g. 'op:mesh.bevel', 'type:Object')",
        command="rna.describe",
        params={"path": Str(required=True, summary="'op:<cat>.<name>' or 'type:<TypeName>'")},
    ),
]
