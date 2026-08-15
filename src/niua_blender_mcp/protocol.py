"""Minimal JSON-RPC + MCP content helpers (zero-dependency stdio transport).

Phase 0 hand-rolls the MCP stdio layer to avoid a dependency tree that may lack
Python 3.14 wheels. The router-based tool surface means swapping in the official
MCP Python SDK later is a transport-only change.

Tool names on the wire use ``domain-action`` (not ``domain.action``). Hosts such
as Grok enforce ``^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$`` and reject dotted names.
They also namespace as ``server__tool``, so a double-underscore domain separator
(``system__health`` → ``blender-finisher__system__health``) collides with that
join and the host drops every tool (tool_count: 0). A single hyphen avoids both
problems. Internal bridge commands keep the dotted form; only the MCP surface
translates.
"""

from __future__ import annotations

import json
import re
from typing import Any

JSON = dict[str, Any]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

#: Hosts (Grok, MCP 2025 tool-name rules) reject ``.`` in tool names.
_MCP_TOOL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$")


def to_mcp_tool_name(name: str) -> str:
    """``domain.action`` → ``domain-action`` (MCP-safe). Already-safe names pass through.

    Uses a hyphen (not ``__``) so host namespacing ``server__tool`` stays unambiguous.
    """
    if not name or "." not in name:
        return name
    domain, rest = name.split(".", 1)
    return f"{domain}-{rest}"


def from_mcp_tool_name(name: str) -> str:
    """``domain-action`` / legacy ``domain__action`` → ``domain.action``.

    Dotted names (legacy callers / bridge form) pass through unchanged.
    """
    if not name or "." in name:
        return name
    # Preferred wire form after the Grok namespace fix.
    if "-" in name:
        domain, rest = name.split("-", 1)
        return f"{domain}.{rest}"
    # Briefly shipped ``domain__action``; still accept it.
    if "__" in name:
        domain, rest = name.split("__", 1)
        return f"{domain}.{rest}"
    return name


def is_mcp_safe_tool_name(name: str) -> bool:
    return bool(name) and _MCP_TOOL_NAME_RE.fullmatch(name) is not None


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def success_response(id_: Any, result: JSON) -> JSON:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def error_response(id_: Any, code: int, message: str, data: Any | None = None) -> JSON:
    error: JSON = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": error}


def text_content(text: str) -> JSON:
    return {"type": "text", "text": text}


def json_text_content(value: Any) -> JSON:
    return text_content(json.dumps(value, indent=2, sort_keys=True))


def image_content(data: str, mime_type: str = "image/png") -> JSON:
    return {"type": "image", "data": data, "mimeType": mime_type}


def _looks_like_image_dict(payload: JSON) -> bool:
    """True when ``payload`` itself is a single captured PNG (not a bundle around images)."""
    if payload.get("encoding") == "base64":
        return True
    mime = payload.get("mimeType")
    if isinstance(mime, str) and mime.startswith("image/"):
        return True
    return bool(payload.get("available") is True and "data" in payload and "images" not in payload)


def redact_image_payloads(value: Any) -> Any:
    """Copy of a tool result with base64 image bytes removed.

    Hosts put both ``content`` text and ``structuredContent`` in the model context.
    Pixels already travel as MCP ``image`` parts — repeating them as JSON doubles the
    token cost (the ~25k-token critique leak).
    """
    if not isinstance(value, dict):
        return value
    out = dict(value)
    if _looks_like_image_dict(out) and "data" in out:
        out.pop("data")
        out["bytes"] = "omitted"
    images = out.get("images")
    if isinstance(images, list):
        redacted: list[Any] = []
        for img in images:
            if isinstance(img, dict) and "data" in img:
                img = dict(img)
                img.pop("data")
                img["bytes"] = "omitted"
            redacted.append(img)
        out["images"] = redacted
    feedback = out.get("_feedback")
    if isinstance(feedback, dict):
        out["_feedback"] = redact_image_payloads(feedback)
    return out
