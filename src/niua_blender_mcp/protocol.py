"""Minimal JSON-RPC + MCP content helpers (zero-dependency stdio transport).

Phase 0 hand-rolls the MCP stdio layer to avoid a dependency tree that may lack
Python 3.14 wheels. The router-based tool surface means swapping in the official
MCP Python SDK later is a transport-only change.
"""

from __future__ import annotations

import json
from typing import Any

JSON = dict[str, Any]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


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
