"""Self-contained structured errors for the add-on.

The add-on is a standalone installable and cannot import the server package, so it
carries its own copy of the error codes. These must stay in sync with
``niua_blender_mcp.kernel.errors`` (a parity test guards this).
"""

from __future__ import annotations

from typing import Any

INVALID_PARAMS = "invalid_params"
NOT_FOUND = "not_found"
PRECONDITION = "precondition_failed"
HANDLER_ERROR = "handler_error"
UNKNOWN_TOOL = "unknown_tool"
PYTHON_DISABLED = "python_disabled"


class BridgeError(Exception):
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
