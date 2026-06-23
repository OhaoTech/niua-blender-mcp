"""Knowledge domain handlers."""

from __future__ import annotations

from ..context import Ctx
from ..core import knowledge
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError


def list_knowledge(ctx: Ctx, payload: dict) -> dict:
    return {"packs": knowledge.list_packs()}


def load(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "name is required")
    try:
        return {"pack": knowledge.load_pack(name)}
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc


COMMANDS = [
    Command("knowledge.list", list_knowledge, mutates=False),
    Command("knowledge.load", load, mutates=False),
]
