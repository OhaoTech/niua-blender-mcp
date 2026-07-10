"""System domain: the gated execute_python escape hatch."""

from __future__ import annotations

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, PYTHON_DISABLED, BridgeError


def execute_python(ctx: Ctx, payload: dict) -> dict:
    if not ctx.allow_python:
        raise BridgeError(
            PYTHON_DISABLED,
            "execute_python is disabled; enable it explicitly for a trusted local session",
        )
    code = payload.get("code")
    if not isinstance(code, str) or not code:
        raise BridgeError(INVALID_PARAMS, "code must be a non-empty string")
    namespace = {"bpy": ctx.bpy}
    exec(code, namespace, namespace)  # noqa: S102 - gated, trusted-local escape hatch
    return {"ok": True}


def health(ctx: Ctx, payload: dict) -> dict:
    from .. import bridge_server  # noqa: PLC0415 - lazy, matches repo style; no import cycle at runtime

    snapshot = bridge_server.health_snapshot()
    snapshot.update(
        {
            "blender_version": getattr(ctx.bpy.app, "version_string", ""),
            "blend_path": getattr(ctx.bpy.data, "filepath", ""),
            "python_enabled": ctx.allow_python,
        }
    )
    return snapshot


COMMANDS = [
    # Wrapped in undo so whatever the snippet mutates is one rollback-able step.
    Command("system.execute_python", execute_python, mutates=True),
    Command("system.health", health, mutates=False, timeout_tier="fast"),
]
