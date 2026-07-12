"""Teaching errors: every error names the fix and the right next call
(detail = {"fix": ..., "next_call": ...}), extending the gates' style to the hands."""

from __future__ import annotations

import types

import pytest

from niua_blender_mcp.kernel.errors import INVALID_PARAMS, UNKNOWN_TOOL
from niua_blender_mcp.server import create_server
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.errors import NOT_FOUND, BridgeError, teach


class RecordingBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        self.calls.append((command, payload))
        return {"ok": True}


def test_teach_builds_a_structured_teaching_error() -> None:
    err = teach(NOT_FOUND, "object not found: Ghost", fix="list the scene", next_call="scene.info")
    assert isinstance(err, BridgeError)
    assert err.code == NOT_FOUND
    assert err.detail == {"fix": "list the scene", "next_call": "scene.info"}


def test_missing_object_error_teaches_scene_info() -> None:
    bpy = types.SimpleNamespace(data=types.SimpleNamespace(objects={}))
    with pytest.raises(BridgeError) as exc:
        Ctx(bpy).get_object("Ghost")
    assert exc.value.code == NOT_FOUND
    assert exc.value.detail["next_call"] == "scene.info"
    assert exc.value.detail["fix"]


def test_unknown_tool_error_teaches_capabilities_tools() -> None:
    server = create_server(bridge=RecordingBridge())
    result = server._tools_call({"name": "nope.nope", "arguments": {}})
    assert result["isError"] is True
    body = result["structuredContent"]
    assert body["code"] == UNKNOWN_TOOL
    assert body["detail"]["next_call"] == "capabilities.tools"


def test_validation_error_names_the_tools_schema() -> None:
    server = create_server(bridge=RecordingBridge())
    result = server._tools_call({"name": "scene.create_object", "arguments": {}})
    body = result["structuredContent"]
    assert body["code"] == INVALID_PARAMS
    # next_call is the bare tool name (an agent must be able to call it verbatim); the
    # argument hint lives in fix instead.
    assert body["detail"]["next_call"] == "capabilities.tools"
    assert "scene.create_object" in body["detail"]["fix"]
