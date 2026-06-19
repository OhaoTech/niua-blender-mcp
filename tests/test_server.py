from __future__ import annotations

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.kernel.errors import INVALID_PARAMS, NOT_FOUND, PYTHON_DISABLED, UNKNOWN_TOOL
from niua_blender_mcp.server import create_server


class RecordingBridge:
    def __init__(self, result=None, raises=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.result = result if result is not None else {"ok": True}
        self.raises = raises

    def call(self, command: str, payload: dict) -> dict:
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
    assert {"scene.info", "scene.create_object", "scene.set_transform", "rna.describe",
            "feedback.capture", "system.execute_python"} <= names


def test_tools_call_validates_and_dispatches() -> None:
    bridge = RecordingBridge(result={"name": "Cube", "type": "MESH"})
    server = create_server(bridge=bridge)
    resp = server.handle(
        rpc("tools/call", {"name": "scene.create_object", "arguments": {"type": "CUBE", "location": [1, 2, 3]}})
    )
    assert resp["result"]["isError"] is False
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


def test_execute_python_blocked_by_default() -> None:
    bridge = RecordingBridge()
    server = create_server(bridge=bridge, allow_python=False)
    resp = server.handle(rpc("tools/call", {"name": "system.execute_python", "arguments": {"code": "1+1"}}))
    assert resp["result"]["isError"] is True
    assert resp["result"]["structuredContent"]["code"] == PYTHON_DISABLED
    assert bridge.calls == []  # never reaches Blender


def test_feedback_capture_returns_image_content() -> None:
    bridge = RecordingBridge(result={"available": True, "mimeType": "image/png", "data": "QkFTRTY0"})
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "feedback.capture", "arguments": {}}))
    content = resp["result"]["content"]
    images = [c for c in content if c["type"] == "image"]
    assert images and images[0]["data"] == "QkFTRTY0"


def test_bridge_error_surfaces_as_tool_error() -> None:
    bridge = RecordingBridge(raises=BridgeError(NOT_FOUND, "object not found: Ghost"))
    server = create_server(bridge=bridge)
    resp = server.handle(rpc("tools/call", {"name": "scene.set_transform", "arguments": {"object": "Ghost"}}))
    assert resp["result"]["isError"] is True
    assert resp["result"]["structuredContent"]["code"] == NOT_FOUND
