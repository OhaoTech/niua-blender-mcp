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


import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import CANCELLED, NOT_FOUND, BridgeError


class FakeBpy:
    def __init__(self) -> None:
        self.app = types.SimpleNamespace(version_string="4.4.0")
        self.data = types.SimpleNamespace(filepath="")
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="": None))


@pytest.fixture(autouse=True)
def _clean_ops():
    bridge_server._OPS.clear()
    yield
    bridge_server._OPS.clear()


def test_op_lifecycle_progress_and_cancel() -> None:
    op = bridge_server._op_start("mesh.heavy")
    ctx = Ctx(FakeBpy(), op=op)
    ctx.progress(0.5, "halfway")
    listed = bridge_server.list_operations()["operations"]
    mine = next(o for o in listed if o["id"] == op["id"])
    assert mine["command"] == "mesh.heavy"
    assert mine["progress"] == 0.5
    assert mine["message"] == "halfway"
    assert mine["done"] is False

    assert bridge_server.cancel_operation(op["id"])["ok"] is True
    assert ctx.cancelled() is True
    with pytest.raises(BridgeError) as exc:
        ctx.check_cancelled()
    assert exc.value.code == CANCELLED

    bridge_server._op_finish(op)
    finished = next(o for o in bridge_server.list_operations()["operations"] if o["id"] == op["id"])
    assert finished["done"] is True and finished["progress"] == 1.0


def test_ctx_without_op_never_cancels() -> None:
    ctx = Ctx(FakeBpy())
    ctx.progress(0.9)  # no-op, must not raise
    assert ctx.cancelled() is False
    ctx.check_cancelled()  # must not raise


def test_cancel_unknown_op_teaches_next_call() -> None:
    response = bridge_server.cancel_operation("op-nope")
    assert response["ok"] is False
    assert response["error"]["code"] == NOT_FOUND
    assert response["error"]["detail"]["next_call"] == "system.operations"


def test_system_operations_and_cancel_are_registered_commands() -> None:
    registry = build_default_registry()
    ctx = Ctx(FakeBpy())
    op = bridge_server._op_start("mesh.heavy")
    listed = dispatch_on_main(registry, "system.operations", {}, ctx)
    assert any(o["id"] == op["id"] for o in listed["operations"])
    result = dispatch_on_main(registry, "system.cancel", {"op_id": op["id"]}, ctx)
    assert result == {"op_id": op["id"], "was_running": True}
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(registry, "system.cancel", {"op_id": "op-nope"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_enqueue_timeout_names_the_op_for_cancellation() -> None:
    response = bridge_server._enqueue("slow.op", {}, 0.05)
    _drain_queue()
    detail = response["error"]["detail"]
    assert detail["op_id"].startswith("op-")
    assert detail["next_call"] == "system.operations"


def test_ops_table_hard_cap_evicts_oldest_even_when_none_are_done() -> None:
    """A wedged main thread never finishes an op, so the done-only eviction in
    _op_start never fires -- the hard cap must still keep the table bounded by
    evicting the oldest not-done records."""
    started = [bridge_server._op_start(f"mesh.heavy.{i}") for i in range(bridge_server._OPS_HARD_CAP + 25)]
    assert len(bridge_server._OPS) <= bridge_server._OPS_HARD_CAP
    # The newest ops must have survived; the oldest were evicted first.
    assert started[-1]["id"] in bridge_server._OPS
    assert started[0]["id"] not in bridge_server._OPS
    assert all(not op["done"] for op in bridge_server._OPS.values())
