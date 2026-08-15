"""System domain: the gated execute_python escape hatch."""

from __future__ import annotations

import contextlib
import io
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, PYTHON_DISABLED, BridgeError

#: Cap on captured output. The escape hatch is often used to dump scene state, and an
#: unbounded ``print`` of every vertex would blow the agent's context in one call.
_MAX_CAPTURE = 16000


def _clip(text: str) -> str:
    if len(text) <= _MAX_CAPTURE:
        return text
    return text[:_MAX_CAPTURE] + f"\n... [{len(text) - _MAX_CAPTURE} more chars truncated]"


def _jsonable(value: Any) -> Any:
    """Best-effort JSON coercion; anything exotic degrades to its repr, never raises."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in list(value.items())[:500]}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in list(value)[:500]]
    try:
        return [_jsonable(v) for v in list(value)[:500]]  # bpy_prop_collection, Vector, ...
    except TypeError:
        return repr(value)[:2000]


def execute_python(ctx: Ctx, payload: dict) -> dict:
    """Run Python inside Blender and report what it printed / produced.

    The point of an escape hatch is reaching what the typed surface cannot express --
    which is as often a *question* ("what are this modifier's vector props?") as a
    mutation. Returning a bare ``{"ok": True}`` made it write-only: every read had to
    be smuggled back out through some other tool. So stdout is captured and returned,
    and a ``result`` variable, if the snippet sets one, comes back JSON-coerced.
    Partial stdout is preserved on failure, since that is usually where the clue is.
    """
    if not ctx.allow_python:
        raise BridgeError(
            PYTHON_DISABLED,
            "execute_python is disabled; enable it explicitly for a trusted local session",
        )
    code = payload.get("code")
    if not isinstance(code, str) or not code:
        raise BridgeError(INVALID_PARAMS, "code must be a non-empty string")
    namespace: dict[str, Any] = {"bpy": ctx.bpy}
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            exec(code, namespace, namespace)  # noqa: S102 - gated, trusted-local escape hatch
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent with its partial output
        raise BridgeError(
            HANDLER_ERROR,
            f"{type(exc).__name__}: {exc}",
            {"stdout": _clip(buffer.getvalue())},
        ) from exc
    out: dict[str, Any] = {"ok": True, "stdout": _clip(buffer.getvalue())}
    if "result" in namespace:
        out["result"] = _jsonable(namespace["result"])
    return out


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


def operations(ctx: Ctx, payload: dict) -> dict:
    from .. import bridge_server  # noqa: PLC0415

    return bridge_server.list_operations()


def cancel(ctx: Ctx, payload: dict) -> dict:
    """Request cooperative cancellation of a queued/running operation (takes effect at
    the operation's next check), by id from system.operations

    Mirrors src/niua_blender_mcp/domains/system.py's system.cancel ToolSpec summary
    (kept textually identical; not parity-checked, but should stay in sync by hand).
    """
    from .. import bridge_server  # noqa: PLC0415
    from ..errors import NOT_FOUND  # noqa: PLC0415

    response = bridge_server.cancel_operation(str(payload.get("op_id") or ""))
    if not response["ok"]:
        error = response["error"]
        raise BridgeError(NOT_FOUND, error["message"], error.get("detail"))
    return response["result"]


COMMANDS = [
    # Wrapped in undo so whatever the snippet mutates is one rollback-able step.
    Command("system.execute_python", execute_python, mutates=True),
    Command("system.health", health, mutates=False, timeout_tier="fast"),
    Command("system.operations", operations, mutates=False, timeout_tier="fast"),
    Command("system.cancel", cancel, mutates=False, timeout_tier="fast"),
]
