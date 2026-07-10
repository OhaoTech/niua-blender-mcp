"""Add-on request-timeout handling and (Task 4) the operation table + cancellation."""

from __future__ import annotations

from niua_mcp_bridge import bridge_server


def _drain_queue() -> None:
    """Leave the module-global request queue empty for other tests."""
    while not bridge_server._REQUESTS.empty():
        bridge_server._REQUESTS.get_nowait()


def test_clamp_timeout_defaults_and_bounds() -> None:
    assert bridge_server._clamp_timeout(None) == 60.0
    assert bridge_server._clamp_timeout("nonsense") == 60.0
    assert bridge_server._clamp_timeout(5.0) == 5.0
    assert bridge_server._clamp_timeout(0.001) == 1.0
    assert bridge_server._clamp_timeout(9999) == 600.0


def test_enqueue_times_out_with_structured_error() -> None:
    # Nothing is draining the queue, so a tiny wait must return the structured
    # timeout error (not hang, not raise).
    response = bridge_server._enqueue("slow.op", {}, 0.05)
    _drain_queue()
    assert response["ok"] is False
    assert response["error"]["code"] == "timeout"
    assert response["error"]["message"].startswith("slow.op exceeded")
