"""Execution context handed to every handler.

Wraps the live ``bpy`` module plus helpers so handlers stay tiny. Future kernel
concerns (context resolver, feedback capture) attach here too.
"""

from __future__ import annotations

from typing import Any

from .errors import NOT_FOUND, BridgeError


class Ctx:
    def __init__(self, bpy_module: Any, allow_python: bool = False, op: dict | None = None) -> None:
        self.bpy = bpy_module
        self.allow_python = allow_python
        self._op = op  # live operation record (bridge_server._op_start); None in bare tests

    def progress(self, fraction: float, message: str = "") -> None:
        """Cooperative progress for long ops; visible via system.operations."""
        if self._op is not None:
            self._op["progress"] = max(0.0, min(float(fraction), 1.0))
            self._op["message"] = str(message)

    def cancelled(self) -> bool:
        return self._op is not None and self._op["cancel"].is_set()

    def check_cancelled(self) -> None:
        """Raise a structured error if system.cancel was called for this operation."""
        if self.cancelled():
            from .errors import CANCELLED  # noqa: PLC0415 - avoid widening the module import surface

            raise BridgeError(
                CANCELLED,
                "operation cancelled by request",
                {"fix": "the partial work (if any) is one undo step away", "next_call": "system.operations"},
            )

    def get_object(self, name: str) -> Any:
        obj = self.bpy.data.objects.get(name)
        if obj is None:
            raise BridgeError(NOT_FOUND, f"object not found: {name}")
        return obj

    def object_summary(self, obj: Any) -> dict[str, Any]:
        return {
            "name": obj.name,
            "type": getattr(obj, "type", ""),
            "location": list(getattr(obj, "location", [])),
            "rotation": list(getattr(obj, "rotation_euler", [])),
            "scale": list(getattr(obj, "scale", [])),
            "visible": not bool(getattr(obj, "hide_viewport", False)),
        }

    def ensure(self, active: Any = None, mode: str | None = None, area: str = "VIEW_3D", select: Any = None):
        """Context manager that sets active/selection/mode/area and restores it.

        Handlers wrap context-sensitive ops in this so they never touch context plumbing::

            with ctx.ensure(active="Cube", mode="EDIT", select=["Cube"]):
                ctx.bpy.ops.mesh.subdivide()
        """
        from .core.context import ensure as _ensure  # lazy: keeps Ctx importable w/o bpy

        return _ensure(active=active, mode=mode, area=area, select=select)

    def check_poll(self, op: Any, message: str | None = None, **override: Any) -> None:
        """Raise a clean precondition error if an operator's poll() is False."""
        from .core.context import check_poll as _check_poll  # lazy

        _check_poll(op, message=message, **override)
