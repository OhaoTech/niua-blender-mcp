"""Asset-class profile command handlers.

A declared policy domain (finishing layer): asset-class budgets/gate overrides are
game-asset policy, so this module is allowed to import from ``..finishing``.
"""

from __future__ import annotations

from ...context import Ctx
from ...dispatch import Command
from ...errors import INVALID_PARAMS, BridgeError
from ...finishing import asset_classes


def list_profiles(ctx: Ctx, payload: dict) -> dict:
    return {
        "asset_classes": [
            {
                "id": profile["id"],
                "label": profile["label"],
                "summary": profile["summary"],
                "profile_version": profile["profile_version"],
            }
            for profile in asset_classes.list_asset_classes()
        ]
    }


def describe(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("asset_class")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "asset_class is required")
    try:
        return {"asset_class": asset_classes.get_asset_class(name)}
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc


COMMANDS = [
    Command("asset_class.list", list_profiles, mutates=False),
    Command("asset_class.describe", describe, mutates=False),
]
