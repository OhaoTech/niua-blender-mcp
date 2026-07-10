"""capabilities.tools: no args -> domain map; {domain} -> its tools; {name} -> one schema.
Answered by the server from the router -- no bridge call ever happens."""

from __future__ import annotations

from niua_blender_mcp.kernel.errors import UNKNOWN_TOOL
from niua_blender_mcp.server import LOCAL_COMMANDS, create_server


class ExplodingBridge:
    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        raise AssertionError(f"capabilities.tools must never hit the bridge (got {command})")


def call(server, arguments: dict) -> dict:
    return server._tools_call({"name": "capabilities.tools", "arguments": arguments})


def test_local_commands_declares_capabilities_tools() -> None:
    assert "capabilities.tools" in LOCAL_COMMANDS


def test_no_args_returns_the_domain_map() -> None:
    server = create_server(bridge=ExplodingBridge())
    result = call(server, {})
    assert result["isError"] is False
    body = result["structuredContent"]
    names = {d["name"] for d in body["domains"]}
    assert {"capabilities", "system", "scene"} <= names
    assert body["total_tools"] > 200
    assert all(d["tool_count"] >= 1 for d in body["domains"])


def test_domain_arg_lists_that_domains_tools() -> None:
    server = create_server(bridge=ExplodingBridge())
    body = call(server, {"domain": "capabilities"})["structuredContent"]
    tool_names = {t["name"] for t in body["tools"]}
    assert "capabilities.tools" in tool_names
    assert "capabilities.search" in tool_names


def test_name_arg_returns_one_full_schema() -> None:
    server = create_server(bridge=ExplodingBridge())
    body = call(server, {"name": "scene.create_object"})["structuredContent"]
    assert body["name"] == "scene.create_object"
    assert body["mutates"] is True
    assert body["timeout_tier"] == "normal"
    assert "type" in body["inputSchema"]["properties"]


def test_unknown_name_teaches_the_next_call() -> None:
    server = create_server(bridge=ExplodingBridge())
    result = call(server, {"name": "nope.nope"})
    assert result["isError"] is True
    body = result["structuredContent"]
    assert body["code"] == UNKNOWN_TOOL
    assert body["detail"]["next_call"] == "capabilities.tools"


def test_unknown_domain_lists_the_valid_domains() -> None:
    server = create_server(bridge=ExplodingBridge())
    result = call(server, {"domain": "nope"})
    assert result["isError"] is True
    assert "capabilities" in result["structuredContent"]["detail"]["domains"]
