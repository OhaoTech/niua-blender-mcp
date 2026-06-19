"""Kernel: the stable core shared by every tool.

Contract (ToolSpec + validation), structured errors, and the router. Transport,
the main-thread queue, undo, context resolution, feedback, and introspection
build on top of these primitives.
"""

from .contract import Bool, Enum, Float, Int, Param, Str, ToolSpec, validate
from .errors import (
    HANDLER_ERROR,
    INVALID_PARAMS,
    NOT_FOUND,
    PRECONDITION,
    McpError,
    ValidationError,
)
from .router import Router

__all__ = [
    "Param",
    "Str",
    "Int",
    "Float",
    "Bool",
    "Enum",
    "ToolSpec",
    "validate",
    "McpError",
    "ValidationError",
    "INVALID_PARAMS",
    "NOT_FOUND",
    "PRECONDITION",
    "HANDLER_ERROR",
    "Router",
]
