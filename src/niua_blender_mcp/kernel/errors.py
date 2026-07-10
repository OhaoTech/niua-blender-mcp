"""Uniform structured error model.

Every failure crossing the bridge or surfacing to the agent is one of these,
serialized as ``{"code": str, "message": str, "detail"?: any}``. Stable codes let
the agent reason about failures instead of parsing prose.
"""

from __future__ import annotations

from typing import Any

INVALID_PARAMS = "invalid_params"
NOT_FOUND = "not_found"
PRECONDITION = "precondition_failed"
HANDLER_ERROR = "handler_error"
TIMEOUT = "timeout"
TRANSPORT = "transport_error"
UNKNOWN_TOOL = "unknown_tool"
PYTHON_DISABLED = "python_disabled"
CANCELLED = "cancelled"


class McpError(Exception):
    """Structured, serializable error."""

    def __init__(self, code: str, message: str, detail: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            data["detail"] = self.detail
        return data


class ValidationError(McpError):
    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(INVALID_PARAMS, message, detail)


class PreconditionError(McpError):
    """Operator/tool preconditions not met (wrong mode, no selection, poll failed)."""

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(PRECONDITION, message, detail)
