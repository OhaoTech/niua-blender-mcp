"""Knowledge domain manifest."""

from __future__ import annotations

from ..asset_classes import ASSET_CLASS_IDS
from ..kernel import Enum, Str, ToolSpec

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
            "asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
        },
    ),
]
