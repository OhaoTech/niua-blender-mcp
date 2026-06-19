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
]
