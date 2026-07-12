"""system.health: liveness, version, queue depth, and the last-error ring buffer."""

from __future__ import annotations

import types

from niua_mcp_bridge import bridge_server
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeBpy:
    def __init__(self) -> None:
        self.app = types.SimpleNamespace(version_string="4.4.0")
        self.data = types.SimpleNamespace(filepath="/tmp/scene.blend")
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="": None))


def test_system_health_reports_liveness_version_queue_and_errors() -> None:
    bridge_server._ERRORS.clear()
    bridge_server._record_error("mesh.boom", {"code": "handler_error", "message": "kaboom"})
    result = dispatch_on_main(build_default_registry(), "system.health", {}, Ctx(FakeBpy()))
    assert result["bridge"] == "alive"
    assert result["blender_version"] == "4.4.0"
    assert result["blend_path"] == "/tmp/scene.blend"
    assert result["queue_depth"] == 0
    assert result["python_enabled"] is False
    assert result["last_errors"][-1]["command"] == "mesh.boom"
    assert result["last_errors"][-1]["code"] == "handler_error"


def test_error_ring_buffer_is_bounded_to_twenty() -> None:
    bridge_server._ERRORS.clear()
    for i in range(30):
        bridge_server._record_error(f"op{i}", {"code": "handler_error", "message": "x"})
    assert len(bridge_server._ERRORS) == 20
    assert bridge_server._ERRORS[0]["command"] == "op10"


def test_enqueue_timeout_lands_in_the_error_ring() -> None:
    bridge_server._ERRORS.clear()
    bridge_server._enqueue("slow.op", {}, 0.05)
    while not bridge_server._REQUESTS.empty():
        bridge_server._REQUESTS.get_nowait()
    assert bridge_server._ERRORS[-1]["command"] == "slow.op"
    assert bridge_server._ERRORS[-1]["code"] == "timeout"
