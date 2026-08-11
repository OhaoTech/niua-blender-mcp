"""MCP wire tool names must be host-safe (no dots, no ``__`` domain join).

Grok enforces ``^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$`` and namespaces tools as
``server__tool``. Dotted names fail the regex; ``domain__action`` collides with
the host join (``blender-finisher__system__health``) and the host keeps 0 tools.
"""

from __future__ import annotations

import re

from niua_blender_mcp.protocol import (
    from_mcp_tool_name,
    is_mcp_safe_tool_name,
    to_mcp_tool_name,
)
from niua_blender_mcp.server import create_server


class _Bridge:
    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        return {"ok": True}


_GROK_TOOL_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$")
_SERVER = "blender-finisher"


def test_to_mcp_tool_name_uses_hyphen() -> None:
    assert to_mcp_tool_name("system.health") == "system-health"
    assert to_mcp_tool_name("shading.set_principled") == "shading-set_principled"
    assert to_mcp_tool_name("already_safe") == "already_safe"


def test_from_mcp_tool_name_round_trips() -> None:
    assert from_mcp_tool_name("system-health") == "system.health"
    assert from_mcp_tool_name("shading-set_principled") == "shading.set_principled"
    assert from_mcp_tool_name("system__health") == "system.health"  # legacy wire form
    assert from_mcp_tool_name("system.health") == "system.health"


def test_all_listed_tools_are_mcp_safe_and_host_namespaceable() -> None:
    server = create_server(bridge=_Bridge())
    names = [t["name"] for t in server._tool_defs()]
    assert names
    for name in names:
        assert is_mcp_safe_tool_name(name), name
        assert _GROK_TOOL_NAME.fullmatch(name), name
        assert len(name) <= 64, name
        assert "." not in name, name
        assert "__" not in name, name  # would collide with server__tool join
        qualified = f"{_SERVER}__{name}"
        assert _GROK_TOOL_NAME.fullmatch(qualified), qualified
        assert len(qualified) <= 64, qualified
        # Host must be able to split server vs tool on the first "__"
        server, tool = qualified.split("__", 1)
        assert server == _SERVER
        assert tool == name
