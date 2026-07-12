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
CANCELLED = "cancelled"


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


def teach(code: str, message: str, *, fix: str, next_call: str, detail: dict[str, Any] | None = None) -> BridgeError:
    """Build a teaching error: every error names the fix and the right next call.

    Use this instead of bare BridgeError wherever the handler knows what the agent
    should do next -- the gates established the style; the hands follow it.
    """
    data: dict[str, Any] = dict(detail or {})
    data["fix"] = fix
    data["next_call"] = next_call
    return BridgeError(code, message, data)
