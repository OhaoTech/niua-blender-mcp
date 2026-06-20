"""The MCP server: turns ToolSpecs into MCP tools and dispatches calls over the bridge.

initialize / tools.list / tools.call / ping, plus empty resources & prompts lists.
Arguments are validated against the ToolSpec before dispatch; results that carry a
capture image are returned as native MCP image content so the agent can see them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from .bridge import BlenderBridge, BridgeError
from .domains import build_router
from .kernel import McpError, Router, validate
from .kernel.errors import PYTHON_DISABLED, UNKNOWN_TOOL
from .prompts import get_prompt, list_prompts
from .protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcError,
    error_response,
    image_content,
    json_text_content,
    success_response,
)

SUPPORTED_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "niua-blender-mcp"
SERVER_VERSION = "0.1.0"

JSON = dict[str, Any]


@dataclass
class NiuaBlenderMCP:
    bridge: Any
    router: Router
    allow_python: bool = False

    # -- JSON-RPC entry ----------------------------------------------------
    def handle(self, request: JSON) -> JSON | None:
        id_ = request.get("id")
        try:
            if request.get("jsonrpc") != "2.0" or "method" not in request:
                raise JsonRpcError(INVALID_REQUEST, "Invalid JSON-RPC request")
            method = request["method"]
            params = request.get("params") or {}
            if "id" not in request:
                return None  # notification
            handler = self._handlers().get(method)
            if handler is None:
                raise JsonRpcError(METHOD_NOT_FOUND, f"Unknown method: {method}")
            return success_response(id_, handler(params))
        except JsonRpcError as exc:
            return error_response(id_, exc.code, exc.message, exc.data)
        except Exception as exc:  # noqa: BLE001
            return error_response(id_, INTERNAL_ERROR, str(exc))

    def _handlers(self) -> dict[str, Callable[[JSON], JSON]]:
        return {
            "initialize": self._initialize,
            "ping": lambda params: {},
            "tools/list": lambda params: {"tools": self._tool_defs()},
            "tools/call": self._tools_call,
            "resources/list": lambda params: {"resources": []},
            "prompts/list": lambda params: {"prompts": list_prompts()},
            "prompts/get": self._prompts_get,
            "logging/setLevel": lambda params: {},
        }

    def _prompts_get(self, params: JSON) -> JSON:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            raise JsonRpcError(INVALID_PARAMS, "prompts/get requires a 'name'")
        try:
            return get_prompt(name, arguments)
        except KeyError:
            raise JsonRpcError(INVALID_PARAMS, f"unknown prompt: {name}") from None

    def _initialize(self, params: JSON) -> JSON:
        return {
            "protocolVersion": SUPPORTED_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": True}, "prompts": {}, "logging": {}},
            "serverInfo": {"name": SERVER_NAME, "title": "Niua Blender MCP", "version": SERVER_VERSION},
            "instructions": "Drive a live Blender: scene.*, rna.describe, feedback.capture.",
        }

    # -- tools -------------------------------------------------------------
    def _tool_defs(self) -> list[JSON]:
        list_all = os.environ.get("NIUA_BLENDER_MCP_LIST_ALL") == "1"
        return [
            {"name": s.name, "description": s.summary, "inputSchema": s.input_schema()}
            for s in self.router.specs()
            if list_all or s.tier != "generated"
        ]

    def _tools_call(self, params: JSON) -> JSON:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        spec = self.router.get(name) if isinstance(name, str) else None
        if spec is None:
            return self._tool_error(UNKNOWN_TOOL, f"unknown tool: {name}")

        try:
            clean = validate(spec, arguments)
        except McpError as exc:
            return self._tool_error(exc.code, exc.message, exc.detail)

        if spec.command == "system.execute_python" and not self.allow_python:
            return self._tool_error(
                PYTHON_DISABLED,
                "system.execute_python is disabled. Set NIUA_BLENDER_MCP_ALLOW_PYTHON=1.",
            )

        try:
            if spec.tier == "generated":
                result = self.bridge.call("capabilities.invoke", {"idname": spec.command, "args": json.dumps(clean)})
            else:
                result = self.bridge.call(spec.command, clean)
        except BridgeError as exc:
            return self._tool_error(exc.code, exc.message, exc.detail)
        return self._tool_result(result)

    def _tool_result(self, result: JSON) -> JSON:
        content = [json_text_content(result)]
        # Single-image path: the result itself, or an attached opt-in capture (_feedback).
        image = result if (result.get("available") and result.get("data")) else result.get("_feedback")
        if isinstance(image, dict) and image.get("available") and image.get("data"):
            content.append(image_content(image["data"], image.get("mimeType", "image/png")))
        # Multi-image path: an 'images' list (multi-angle / turntable). Append one image
        # content per available image so a multimodal agent sees every angle at once.
        images = result.get("images")
        if isinstance(images, list):
            for img in images:
                if isinstance(img, dict) and img.get("data"):
                    content.append(image_content(img["data"], img.get("mimeType", "image/png")))
        return {"content": content, "structuredContent": result, "isError": False}

    def _tool_error(self, code: str, message: str, detail: Any | None = None) -> JSON:
        structured: JSON = {"code": code, "message": message}
        if detail is not None:
            structured["detail"] = detail
        return {"content": [json_text_content(structured)], "structuredContent": structured, "isError": True}


def create_server(
    bridge: Any | None = None,
    router: Router | None = None,
    allow_python: bool | None = None,
) -> NiuaBlenderMCP:
    if allow_python is None:
        allow_python = os.environ.get("NIUA_BLENDER_MCP_ALLOW_PYTHON") == "1"
    return NiuaBlenderMCP(
        bridge=bridge or BlenderBridge(),
        router=router or build_router(),
        allow_python=allow_python,
    )
