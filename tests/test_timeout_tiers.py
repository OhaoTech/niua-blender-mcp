"""Per-call timeout tiers: ToolSpec declares fast/normal/heavy, the server enforces
per spec, and the bridge carries the chosen timeout on the wire so the add-on's
main-thread wait matches (add-on side is Task 2 / tests/test_dispatch.py)."""

from __future__ import annotations

import contextlib
import json
import socket
import threading

import pytest

from niua_blender_mcp.bridge import BlenderBridge
from niua_blender_mcp.domains import build_router
from niua_blender_mcp.kernel import TIMEOUT_SECONDS, Router, ToolSpec
from niua_blender_mcp.server import create_server


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


class RecordingBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.timeouts: list[float | None] = []

    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        self.calls.append((command, payload))
        self.timeouts.append(timeout)
        return {"ok": True}


def test_timeout_tier_default_is_normal() -> None:
    spec = ToolSpec(name="x.y", category="x", summary="s", command="x.y")
    assert spec.timeout_tier == "normal"


def test_unknown_timeout_tier_rejected() -> None:
    with pytest.raises(ValueError, match="unknown timeout tier"):
        ToolSpec(name="x.y", category="x", summary="s", command="x.y", timeout_tier="slow")


def test_tier_seconds_are_fast_normal_heavy() -> None:
    assert TIMEOUT_SECONDS == {"fast": 5.0, "normal": 60.0, "heavy": 600.0}


def test_per_call_timeout_travels_on_the_wire() -> None:
    seen: dict = {}

    def responder(request):
        seen.update(request)
        return {"ok": True, "result": {}}

    with fake_server(responder) as port:
        BlenderBridge(port=port).call("scene.info", {}, timeout=600.0)
    assert seen["timeout"] == 600.0


def test_default_timeout_travels_on_the_wire_too() -> None:
    seen: dict = {}

    def responder(request):
        seen.update(request)
        return {"ok": True, "result": {}}

    with fake_server(responder) as port:
        BlenderBridge(port=port, timeout=30.0).call("scene.info", {})
    assert seen["timeout"] == 30.0


def test_server_dispatches_tier_timeouts() -> None:
    router = Router()
    router.add(
        [
            ToolSpec(name="t.heavy", category="t", summary="s", command="t.heavy", timeout_tier="heavy"),
            ToolSpec(name="t.fast", category="t", summary="s", command="t.fast", timeout_tier="fast"),
            ToolSpec(name="t.normal", category="t", summary="s", command="t.normal"),
        ]
    )
    bridge = RecordingBridge()
    server = create_server(bridge=bridge, router=router)
    server._tools_call({"name": "t.heavy", "arguments": {}})
    server._tools_call({"name": "t.fast", "arguments": {}})
    server._tools_call({"name": "t.normal", "arguments": {}})
    assert bridge.timeouts == [600.0, 5.0, 60.0]


def test_heavy_measure_and_io_tools_are_marked_heavy() -> None:
    router = build_router()
    heavy = [
        "feedback.quality",
        "feedback.readiness",
        "feedback.preservation",
        "feedback.capture_intake",
        "feedback.critique",
        "io.import",
        "io.export",
        "io.prepare_asset",
    ]
    for name in heavy:
        assert router.get(name).timeout_tier == "heavy", name
