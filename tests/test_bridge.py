from __future__ import annotations

import contextlib
import json
import socket
import threading

import pytest

from niua_blender_mcp.bridge import BlenderBridge, BridgeError
from niua_blender_mcp.kernel.errors import NOT_FOUND, TRANSPORT


@contextlib.contextmanager
def fake_server(responder):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        with contextlib.suppress(OSError):
            conn, _ = srv.accept()
            with conn:
                line = conn.makefile("rb").readline()
                request = json.loads(line.decode("utf-8"))
                conn.sendall((json.dumps(responder(request)) + "\n").encode("utf-8"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        srv.close()
        thread.join(timeout=2)


def test_call_round_trips_a_command() -> None:
    with fake_server(lambda req: {"ok": True, "result": {"echo": req["command"], "p": req["payload"]}}) as port:
        bridge = BlenderBridge(port=port)
        result = bridge.call("scene.info", {"x": 1})
    assert result == {"echo": "scene.info", "p": {"x": 1}}


def test_error_response_raises_bridge_error_with_code() -> None:
    with fake_server(lambda req: {"ok": False, "error": {"code": NOT_FOUND, "message": "no object"}}) as port:
        bridge = BlenderBridge(port=port)
        with pytest.raises(BridgeError) as exc:
            bridge.call("scene.set_transform", {"object": "Ghost"})
    assert exc.value.code == NOT_FOUND


def test_unreachable_bridge_raises_transport_error() -> None:
    # Bind then close to obtain a definitely-closed port.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    closed_port = s.getsockname()[1]
    s.close()
    bridge = BlenderBridge(port=closed_port, timeout=1.0)
    with pytest.raises(BridgeError) as exc:
        bridge.call("scene.info", {})
    assert exc.value.code == TRANSPORT
