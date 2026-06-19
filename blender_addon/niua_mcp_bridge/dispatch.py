"""Command registry + main-thread dispatch with per-op undo.

``dispatch_on_main`` is what the timer callback runs on Blender's main thread. Every
mutating command is wrapped in a single Blender undo step so a failure rolls back and
a success leaves exactly one undo step (the human can Ctrl+Z any agent action).
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

    if not command.mutates:
        return _run(command, ctx, payload)

    ctx.bpy.ops.ed.undo_push(message=f"niua:{command_name}")
    try:
        return _run(command, ctx, payload)
    except BaseException:
        try:
            ctx.bpy.ops.ed.undo()  # roll back the partial mutation
        except Exception:
            pass
        raise
