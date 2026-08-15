from __future__ import annotations

import json

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.kernel.errors import INVALID_PARAMS, NOT_FOUND, PYTHON_DISABLED, UNKNOWN_TOOL
from niua_blender_mcp.server import create_server


class RecordingBridge:
    def __init__(self, result=None, raises=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.result = result if result is not None else {"ok": True}
        self.raises = raises

    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        self.calls.append((command, payload))
        if self.raises is not None:
            raise self.raises
        return dict(self.result)


def rpc(method: str, params: dict | None = None) -> dict:
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request["params"] = params
    return request


def test_tools_list_exposes_the_manifest() -> None:
    server = create_server(bridge=RecordingBridge())
    names = {t["name"] for t in server.handle(rpc("tools/list"))["result"]["tools"]}
    # Wire names are MCP-safe (domain-action); hosts like Grok reject dotted names
    # and also break on domain__action because they namespace as server__tool.
    assert {
        "scene-info",
        "scene-create_object",
        "scene-set_transform",
        "rna-describe",
        "feedback-capture",
        "system-execute_python",
    } <= names
    assert not any("." in n for n in names)


def test_tools_call_validates_and_dispatches() -> None:
    bridge = RecordingBridge(result={"name": "Cube", "type": "MESH"})
    server = create_server(bridge=bridge)
    resp = server.handle(
        rpc("tools/call", {"name": "scene.create_object", "arguments": {"type": "CUBE", "location": [1, 2, 3]}})
    )
    assert resp["result"]["isError"] is False
    assert bridge.calls[-1] == ("scene.create_object", {"type": "CUBE", "location": [1.0, 2.0, 3.0]})


def test_tools_call_accepts_mcp_safe_names() -> None:
    bridge = RecordingBridge(result={"name": "Cube", "type": "MESH"})
    server = create_server(bridge=bridge)
    for wire_name in ("scene-create_object", "scene__create_object"):
        bridge.calls.clear()
        resp = server.handle(
            rpc(
                "tools/call",
                {"name": wire_name, "arguments": {"type": "CUBE", "location": [1, 2, 3]}},
            )
        )
        assert resp["result"]["isError"] is False, wire_name
        assert bridge.calls[-1] == ("scene.create_object", {"type": "CUBE", "location": [1.0, 2.0, 3.0]})


def test_invalid_arguments_return_tool_error_without_dispatch() -> None:
    bridge = RecordingBridge()
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "scene.create_object", "arguments": {}}))
    assert resp["result"]["isError"] is True
    assert resp["result"]["structuredContent"]["code"] == INVALID_PARAMS
    assert bridge.calls == []


def test_unknown_tool_returns_error() -> None:
    server = create_server(bridge=RecordingBridge())
    resp = server.handle(rpc("tools/call", {"name": "nope", "arguments": {}}))
    assert resp["result"]["isError"] is True
    assert resp["result"]["structuredContent"]["code"] == UNKNOWN_TOOL


def test_execute_python_blocked_when_explicitly_disabled() -> None:
    bridge = RecordingBridge()
    server = create_server(bridge=bridge, allow_python=False)
    resp = server.handle(rpc("tools/call", {"name": "system.execute_python", "arguments": {"code": "1+1"}}))
    assert resp["result"]["isError"] is True
    assert resp["result"]["structuredContent"]["code"] == PYTHON_DISABLED
    assert bridge.calls == []  # never reaches Blender


def test_execute_python_is_allowed_by_default(monkeypatch) -> None:
    """The agent escape hatch is open unless someone closes it deliberately."""
    monkeypatch.delenv("NIUA_BLENDER_MCP_ALLOW_PYTHON", raising=False)
    bridge = RecordingBridge()
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "system.execute_python", "arguments": {"code": "1+1"}}))
    assert resp["result"]["isError"] is False
    assert bridge.calls and bridge.calls[0][0] == "system.execute_python"


def test_execute_python_env_var_can_close_the_gate(monkeypatch) -> None:
    for value in ("0", "false", "off", "no"):
        monkeypatch.setenv("NIUA_BLENDER_MCP_ALLOW_PYTHON", value)
        bridge = RecordingBridge()
        server = create_server(bridge=bridge)
        resp = server.handle(rpc("tools/call", {"name": "system.execute_python", "arguments": {"code": "1+1"}}))
        assert resp["result"]["structuredContent"]["code"] == PYTHON_DISABLED, value
        assert bridge.calls == [], value


def test_health_reports_the_effective_python_gate_not_just_the_bridges(monkeypatch) -> None:
    """Blender's half saying yes must not read as 'enabled' when the server says no.

    That mismatch is what made the add-on preference look effective while every
    execute_python call still failed at the server.
    """
    monkeypatch.setenv("NIUA_BLENDER_MCP_ALLOW_PYTHON", "0")
    bridge = RecordingBridge(result={"bridge": "alive", "python_enabled": True})
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "system.health", "arguments": {}}))
    assert resp["result"]["structuredContent"]["python_enabled"] is False

    monkeypatch.delenv("NIUA_BLENDER_MCP_ALLOW_PYTHON", raising=False)
    server = create_server(bridge=RecordingBridge(result={"bridge": "alive", "python_enabled": True}))
    resp = server.handle(rpc("tools/call", {"name": "system.health", "arguments": {}}))
    assert resp["result"]["structuredContent"]["python_enabled"] is True


def test_health_reports_false_when_only_blender_side_refuses(monkeypatch) -> None:
    monkeypatch.delenv("NIUA_BLENDER_MCP_ALLOW_PYTHON", raising=False)
    bridge = RecordingBridge(result={"bridge": "alive", "python_enabled": False})
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "system.health", "arguments": {}}))
    assert resp["result"]["structuredContent"]["python_enabled"] is False


def test_feedback_capture_returns_image_content() -> None:
    bridge = RecordingBridge(result={"available": True, "mimeType": "image/png", "data": "QkFTRTY0"})
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "feedback.capture", "arguments": {}}))
    content = resp["result"]["content"]
    images = [c for c in content if c["type"] == "image"]
    assert images and images[0]["data"] == "QkFTRTY0"


def test_feedback_capture_does_not_repeat_base64_in_json() -> None:
    """Images travel as MCP image parts. The JSON/text envelope must not also dump bytes."""
    payload = "QkFTRTY0" * 40  # long enough that a leak would be obvious
    bridge = RecordingBridge(result={"available": True, "view": "front", "mimeType": "image/png", "data": payload})
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "feedback.capture", "arguments": {}}))
    result = resp["result"]
    text_parts = [c["text"] for c in result["content"] if c.get("type") == "text"]
    assert all(payload not in text for text in text_parts)
    structured = result["structuredContent"]
    assert payload not in str(structured)
    assert structured.get("data") != payload
    assert structured["available"] is True
    assert structured["view"] == "front"
    images = [c for c in result["content"] if c["type"] == "image"]
    assert images and images[0]["data"] == payload


def test_capture_views_returns_one_image_content_per_image() -> None:
    bridge = RecordingBridge(
        result={
            "available": True,
            "images": [
                {"view": "front", "mimeType": "image/png", "data": "Rk9OVA=="},
                {"view": "right", "mimeType": "image/png", "data": "UklHSFQ="},
                {"view": "broken", "available": False, "reason": "no gpu"},  # no data -> skipped
            ],
        }
    )
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "feedback.capture_views", "arguments": {}}))
    content = resp["result"]["content"]
    images = [c for c in content if c["type"] == "image"]
    assert [i["data"] for i in images] == ["Rk9OVA==", "UklHSFQ="]
    assert resp["result"]["isError"] is False


def test_critique_bundle_json_omits_image_bytes() -> None:
    """feedback.critique's 4-view bundle must not dump base64 into the text/structured JSON."""
    front = "FRONT64" * 30
    right = "RIGHT64" * 30
    bridge = RecordingBridge(
        result={
            "available": True,
            "images": [
                {"view": "front", "mimeType": "image/png", "encoding": "base64", "data": front},
                {"view": "right", "mimeType": "image/png", "encoding": "base64", "data": right},
            ],
            "report": {"object": "chair_wooden", "vertices": 8, "quality": {"quad_ratio": 1.0}},
            "uv": {"object": "chair_wooden", "has_uvs": True},
        }
    )
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "feedback.critique", "arguments": {"object": "chair_wooden"}}))
    result = resp["result"]
    blob = json.dumps(result["structuredContent"]) + "".join(
        c.get("text", "") for c in result["content"] if c.get("type") == "text"
    )
    assert front not in blob
    assert right not in blob
    structured = result["structuredContent"]
    assert [img["view"] for img in structured["images"]] == ["front", "right"]
    assert all("data" not in img or img["data"] != front for img in structured["images"])
    assert structured["report"]["object"] == "chair_wooden"
    assert structured["uv"]["has_uvs"] is True
    images = [c for c in result["content"] if c["type"] == "image"]
    assert [i["data"] for i in images] == [front, right]


def test_bridge_error_surfaces_as_tool_error() -> None:
    bridge = RecordingBridge(raises=BridgeError(NOT_FOUND, "object not found: Ghost"))
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "scene.set_transform", "arguments": {"object": "Ghost"}}))
    assert resp["result"]["isError"] is True
    assert resp["result"]["structuredContent"]["code"] == NOT_FOUND


def test_generated_tools_hidden_from_list_by_default(monkeypatch) -> None:
    monkeypatch.delenv("NIUA_BLENDER_MCP_LIST_ALL", raising=False)
    server = create_server(bridge=RecordingBridge())
    listed = {t["name"] for t in server._tool_defs()}
    assert not any(
        t.startswith("modeling.") or t.startswith("modeling__") or t.startswith("modeling-")
        for t in listed
    )
    assert "capabilities-search" in listed


def test_generated_tool_routes_through_invoke() -> None:
    bridge = RecordingBridge()
    server = create_server(bridge=bridge)
    server._tools_call({"name": "modeling.subdivide", "arguments": {"number_cuts": 3}})
    command, payload = bridge.calls[-1]
    assert command == "capabilities.invoke"
    assert payload["idname"] == "mesh.subdivide"
    assert '"number_cuts": 3' in payload["args"]
