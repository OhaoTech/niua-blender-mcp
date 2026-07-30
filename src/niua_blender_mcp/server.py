"""The MCP server: turns ToolSpecs into MCP tools and dispatches calls over the bridge.

initialize / tools.list / tools.call / ping, plus empty resources & prompts lists.
Arguments are validated against the ToolSpec before dispatch; results that carry a
capture image are returned as native MCP image content so the agent can see them.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from .bridge import BlenderBridge, BridgeError
from .domains import build_router
from .kernel import TIMEOUT_SECONDS, McpError, Router, validate
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
from .session_log import from_env, summarize_result

SUPPORTED_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "niua-blender-finisher"
SERVER_VERSION = "0.2.1"

#: Tools the server answers itself from the router -- no bridge round-trip, usable with
#: Blender down. tests/test_parity.py exempts these from the add-on-handler mirror.
LOCAL_COMMANDS = frozenset({"capabilities.tools"})

JSON = dict[str, Any]


@dataclass
class NiuaBlenderMCP:
    bridge: Any
    router: Router
    allow_python: bool = False
    session_log: Any = None

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
            "serverInfo": {"name": SERVER_NAME, "title": "Niua Blender Finisher", "version": SERVER_VERSION},
            "instructions": "Niua Blender Finisher: scene.*, rna.describe, feedback.capture, bake_and_finish.",
        }

    # -- tools -------------------------------------------------------------
    def _tool_defs(self) -> list[JSON]:
        list_all = os.environ.get("NIUA_BLENDER_MCP_LIST_ALL") == "1"
        return [
            {"name": s.name, "description": s.summary, "inputSchema": s.input_schema()}
            for s in self.router.specs()
            if list_all or s.tier != "generated"
        ]

    def _describe_tools(self, args: JSON) -> JSON:
        """capabilities.tools: no args -> domain map; {domain} -> its tools; {name} -> one schema."""
        name = args.get("name") or ""
        domain = args.get("domain") or ""
        specs = self.router.specs()
        if name:
            spec = self.router.get(name)
            if spec is None:
                close = sorted(s.name for s in specs if name.lower() in s.name.lower())[:10]
                return self._tool_error(
                    UNKNOWN_TOOL,
                    f"unknown tool: {name}",
                    {"close_matches": close, "fix": "browse the domain map first", "next_call": "capabilities.tools"},
                )
            return self._tool_result(
                {
                    "name": spec.name,
                    "summary": spec.summary,
                    "domain": spec.category,
                    "tier": spec.tier,
                    "mutates": spec.mutates,
                    "timeout_tier": spec.timeout_tier,
                    "inputSchema": spec.input_schema(),
                }
            )
        if domain:
            tools = sorted(
                (
                    {"name": s.name, "summary": s.summary, "mutates": s.mutates}
                    for s in specs
                    if s.category == domain
                ),
                key=lambda t: t["name"],
            )
            if not tools:
                return self._tool_error(
                    UNKNOWN_TOOL,
                    f"unknown domain: {domain}",
                    {
                        "domains": sorted({s.category for s in specs}),
                        "fix": "pick a domain from the list",
                        "next_call": "capabilities.tools",
                    },
                )
            return self._tool_result(
                {
                    "domain": domain,
                    "tools": tools,
                    "next": 'call capabilities.tools {"name": "<tool>"} for one schema',
                }
            )
        by_domain: dict[str, int] = {}
        for s in specs:
            by_domain[s.category] = by_domain.get(s.category, 0) + 1
        return self._tool_result(
            {
                "domains": [{"name": d, "tool_count": n} for d, n in sorted(by_domain.items())],
                "total_tools": len(specs),
                "next": 'call capabilities.tools {"domain": "<name>"} to list its tools',
            }
        )

    def _tools_call(self, params: JSON) -> JSON:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        spec = self.router.get(name) if isinstance(name, str) else None
        if spec is None:
            return self._tool_error(
                UNKNOWN_TOOL,
                f"unknown tool: {name}",
                {"fix": "navigate the tool surface first", "next_call": "capabilities.tools"},
            )

        try:
            clean = validate(spec, arguments)
        except McpError as exc:
            detail: JSON = dict(exc.detail) if isinstance(exc.detail, dict) else (
                {} if exc.detail is None else {"got": exc.detail}
            )
            detail.setdefault(
                "fix",
                f"correct the argument and re-call {spec.name}; "
                f'call capabilities.tools {{"name": "{spec.name}"}} to see its schema',
            )
            detail.setdefault("next_call", "capabilities.tools")
            return self._tool_error(exc.code, exc.message, detail)

        if spec.command in LOCAL_COMMANDS:
            return self._describe_tools(clean)

        if spec.command == "system.execute_python" and not self.allow_python:
            return self._tool_error(
                PYTHON_DISABLED,
                "system.execute_python is disabled. Set NIUA_BLENDER_MCP_ALLOW_PYTHON=1.",
            )

        timeout = TIMEOUT_SECONDS[spec.timeout_tier]
        started = time.perf_counter()
        try:
            if spec.tier == "generated":
                result = self.bridge.call(
                    "capabilities.invoke",
                    {"idname": spec.command, "args": json.dumps(clean)},
                    timeout=timeout,
                )
            else:
                result = self.bridge.call(spec.command, clean, timeout=timeout)
        except BridgeError as exc:
            self._record_session(spec, clean, started, ok=False, error=exc)
            return self._tool_error(exc.code, exc.message, exc.detail)
        self._record_session(spec, clean, started, ok=True, result=result)
        return self._tool_result(result)

    def _record_session(self, spec, arguments: JSON, started: float, *, ok: bool,
                        result: JSON | None = None, error: BridgeError | None = None) -> None:
        # Zero-cost when off: the guard runs before ANY summarize/thumbnail work.
        if self.session_log is None or not spec.mutates:
            return
        try:
            if error is not None:
                summary: JSON = {"code": error.code, "message": error.message}
                thumbnail = None
            else:
                summary = summarize_result(result or {})
                thumbnail = self._session_thumbnail(result or {})
            self.session_log.record(
                tool=spec.name,
                arguments=arguments,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                ok=ok,
                summary=summary,
                thumbnail=thumbnail,
            )
        except Exception:  # noqa: BLE001 -- logging must never break a dispatch
            pass

    @staticmethod
    def _session_thumbnail(result: JSON) -> str | None:
        image = result if (result.get("available") and result.get("data")) else result.get("_feedback")
        if isinstance(image, dict) and image.get("available") and image.get("data"):
            return str(image["data"])
        return None

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
    session_log: Any | None = None,
) -> NiuaBlenderMCP:
    if allow_python is None:
        allow_python = os.environ.get("NIUA_BLENDER_MCP_ALLOW_PYTHON") == "1"
    return NiuaBlenderMCP(
        bridge=bridge or BlenderBridge(),
        router=router or build_router(),
        allow_python=allow_python,
        session_log=session_log if session_log is not None else from_env(),
    )
