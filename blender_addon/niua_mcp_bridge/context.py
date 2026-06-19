"""Execution context handed to every handler.

Wraps the live ``bpy`` module plus helpers so handlers stay tiny. Future kernel
concerns (context resolver, feedback capture) attach here too.
"""

from __future__ import annotations

from typing import Any

from .errors import NOT_FOUND, BridgeError


class Ctx:
    def __init__(self, bpy_module: Any, allow_python: bool = False) -> None:
        self.bpy = bpy_module
        self.allow_python = allow_python

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
