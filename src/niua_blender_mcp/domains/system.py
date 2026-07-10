"""System domain manifest: the gated execute_python escape hatch."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="system.execute_python",
        category="system",
        summary="Run Python inside Blender (disabled unless explicitly enabled)",
        command="system.execute_python",
        params={"code": Str(required=True, summary="Python source to exec")},
        mutates=True,
    ),
    ToolSpec(
        name="system.health",
        category="system",
        summary="Bridge health: Blender version, open .blend, queue depth, last-error ring buffer",
        command="system.health",
        timeout_tier="fast",
    ),
    ToolSpec(
        name="system.operations",
        category="system",
        summary="List in-flight and recent operations with progress (works even while the main thread is busy)",
        command="system.operations",
        timeout_tier="fast",
    ),
    ToolSpec(
        name="system.cancel",
        category="system",
        summary="Request cancellation of a running operation by id (from system.operations)",
        command="system.cancel",
        params={"op_id": Str(required=True, summary="Operation id, e.g. 'op-7'")},
        timeout_tier="fast",
    ),
]
