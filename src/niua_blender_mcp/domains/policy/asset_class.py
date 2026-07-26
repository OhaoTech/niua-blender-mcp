"""Asset-class profile tool manifest."""

from __future__ import annotations

from ...finishing.asset_classes import ASSET_CLASS_IDS
from ...kernel import Enum, ToolSpec

SPECS = [
    ToolSpec(
        name="asset_class.list",
        category="asset_class",
        summary="List Layer 2 game-asset class profiles",
        command="asset_class.list",
    ),
    ToolSpec(
        name="asset_class.describe",
        category="asset_class",
        summary="Describe one Layer 2 game-asset class profile",
        command="asset_class.describe",
        params={
            "asset_class": Enum(ASSET_CLASS_IDS, required=True, summary="Asset class profile id"),
        },
    ),
]
