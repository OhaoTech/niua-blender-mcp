"""Command registry + main-thread dispatch with per-op undo.

``dispatch_on_main`` is what the timer callback runs on Blender's main thread. A
successful mutation pushes exactly one named Blender undo step, so the human can
Ctrl+Z any agent action.

Undo is pushed AFTER success, not before. Pushing before and calling undo() on failure
is wrong in real Blender: when a handler fails *before* mutating (e.g. object not
found), undo() steps back past the empty checkpoint and reverts the *previous*
legitimate operation (this was caught in live GUI testing). Phase-0 handlers
validate-then-act on a single op, so a failure means nothing mutated and there is
nothing to roll back. Multi-step rollback is a per-domain transaction concern in
Phase 1 (bmesh edits are naturally transactional).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .context import Ctx
from .errors import HANDLER_ERROR, UNKNOWN_TOOL, BridgeError

Handler = Callable[[Ctx, dict], dict]


@dataclass(frozen=True)
class Command:
    name: str
    handler: Handler
    mutates: bool = False
    feedback: str | None = None


class Registry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        self._commands[command.name] = command

    def add(self, commands: list[Command]) -> None:
        for command in commands:
            self.register(command)

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def names(self) -> set[str]:
        return set(self._commands)


def _run(command: Command, ctx: Ctx, payload: dict) -> dict:
    try:
        return command.handler(ctx, payload)
    except BridgeError:
        raise
    except Exception as exc:  # normalize anything unexpected
        raise BridgeError(HANDLER_ERROR, str(exc)) from exc


def dispatch_on_main(registry: Registry, command_name: str, payload: dict | None, ctx: Ctx) -> dict:
    command = registry.get(command_name)
    if command is None:
        raise BridgeError(UNKNOWN_TOOL, f"unknown command: {command_name}")
    payload = payload or {}

    # Precondition failures raise here, before any mutation and before any undo push.
    result = _run(command, ctx, payload)

    if command.mutates:
        # One named undo step per successful agent action (clean Ctrl+Z).
        ctx.bpy.ops.ed.undo_push(message=f"niua:{command_name}")
    return result
