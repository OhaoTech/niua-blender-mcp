"""Knowledge domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="knowledge.list",
        category="knowledge",
        summary="List grounded Layer 2 knowledge packs",
        command="knowledge.list",
    ),
    ToolSpec(
        name="knowledge.load",
        category="knowledge",
        summary="Load a grounded Layer 2 knowledge pack by name",
        command="knowledge.load",
        params={
            "name": Str(required=True, summary="Knowledge pack name"),
        },
    ),
]
