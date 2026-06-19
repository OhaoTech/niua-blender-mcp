"""MCP protocol coverage for prompts (prompts/list + prompts/get) and the loop scaffold.

The server used to return an empty prompts list; these assert the two real prompts
(refine_mesh, inspect) are advertised, render to user messages, scaffold the
checkpoint -> edit -> critique/quality -> judge -> keep/revert loop, accept an optional
'object' argument, and that the prompts capability is announced in initialize.
"""

from __future__ import annotations

from niua_blender_mcp.protocol import INVALID_PARAMS as RPC_INVALID_PARAMS
from niua_blender_mcp.server import create_server


class StubBridge:
    def call(self, command, payload):  # pragma: no cover - prompts never hit the bridge
        return {}


def rpc(method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request["params"] = params
    return request


def _server():
    return create_server(bridge=StubBridge())


def test_initialize_announces_prompts_capability() -> None:
    server = _server()
    caps = server.handle(rpc("initialize"))["result"]["capabilities"]
    assert "prompts" in caps


def test_prompts_list_exposes_the_loop_prompts() -> None:
    server = _server()
    prompts = server.handle(rpc("prompts/list"))["result"]["prompts"]
    names = {p["name"] for p in prompts}
    assert {"refine_mesh", "inspect"} <= names
    # Each prompt advertises an optional 'object' argument.
    for p in prompts:
        arg_names = {a["name"] for a in p["arguments"]}
        assert "object" in arg_names
        assert all(a["required"] is False for a in p["arguments"])


def test_prompts_get_refine_mesh_scaffolds_the_loop() -> None:
    server = _server()
    res = server.handle(rpc("prompts/get", {"name": "refine_mesh"}))["result"]
    assert res["messages"][0]["role"] == "user"
    text = res["messages"][0]["content"]["text"]
    # The loop primitives are named in the scaffold.
    for token in ("session.checkpoint", "feedback.critique", "feedback.quality", "session.revert"):
        assert token in text
    # No object given -> defaults to the active object.
    assert "active object" in text


def test_prompts_get_inspect_is_read_only_scaffold() -> None:
    server = _server()
    text = server.handle(rpc("prompts/get", {"name": "inspect"}))["result"]["messages"][0]["content"]["text"]
    for token in ("scene.info", "feedback.critique", "feedback.quality"):
        assert token in text
    assert "READ-ONLY" in text


def test_prompts_get_accepts_object_argument() -> None:
    server = _server()
    res = server.handle(rpc("prompts/get", {"name": "refine_mesh", "arguments": {"object": "Hero"}}))
    text = res["result"]["messages"][0]["content"]["text"]
    assert "'Hero'" in text
    assert '"object": "Hero"' in text


def test_prompts_get_unknown_name_errors() -> None:
    server = _server()
    resp = server.handle(rpc("prompts/get", {"name": "does_not_exist"}))
    assert resp["error"]["code"] == RPC_INVALID_PARAMS


def test_prompts_get_missing_name_errors() -> None:
    server = _server()
    resp = server.handle(rpc("prompts/get", {}))
    assert resp["error"]["code"] == RPC_INVALID_PARAMS
