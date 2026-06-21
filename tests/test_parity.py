"""Guard against server/add-on command drift: every server tool's command must
have a matching add-on handler, and vice versa."""

from __future__ import annotations

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.domains import build_default_registry


def test_server_commands_match_addon_handlers() -> None:
    server_commands = {
        "capabilities.invoke" if spec.tier == "generated" else spec.command
        for spec in build_router().specs()
    }
    addon_commands = build_default_registry().names()
    assert server_commands == addon_commands


def test_server_command_metadata_matches_addon_handlers() -> None:
    registry = build_default_registry()
    for spec in build_router().specs():
        command_name = "capabilities.invoke" if spec.tier == "generated" else spec.command
        command = registry.get(command_name)
        assert command is not None
        assert command.mutates == spec.mutates, command_name
        assert command.feedback == spec.feedback, command_name
