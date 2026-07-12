"""Supervisor state machine: probe -> degraded -> relaunch + session restore."""

from __future__ import annotations

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.kernel.errors import TIMEOUT, TRANSPORT
from niua_blender_mcp.supervisor import Supervisor


class Harness:
    def __init__(self, health: dict | None = None) -> None:
        self.health = health or {"bridge": "alive", "blend_path": ""}
        self.fail = False
        self.relaunches = 0
        self.restored: list[str] = []

    def probe(self) -> dict:
        if self.fail:
            raise ConnectionError("bridge down")
        return self.health

    def relaunch(self) -> None:
        self.relaunches += 1
        self.fail = False  # a fresh Blender answers again

    def restore(self, path: str) -> None:
        self.restored.append(path)


def make(harness: Harness, max_failures: int = 3) -> Supervisor:
    return Supervisor(
        probe=harness.probe, relaunch=harness.relaunch, restore=harness.restore, max_failures=max_failures
    )


def test_healthy_tick_remembers_the_open_blend() -> None:
    h = Harness({"bridge": "alive", "blend_path": "/tmp/hero.blend"})
    s = make(h)
    assert s.tick() == "healthy"
    assert s.last_blend_path == "/tmp/hero.blend"
    assert h.relaunches == 0


def test_failures_below_threshold_only_degrade() -> None:
    h = Harness()
    s = make(h, max_failures=3)
    h.fail = True
    assert s.tick() == "degraded"
    assert s.tick() == "degraded"
    assert h.relaunches == 0
    assert s.failures == 2


def test_threshold_failure_relaunches_and_restores_last_blend() -> None:
    h = Harness({"bridge": "alive", "blend_path": "/tmp/hero.blend"})
    s = make(h, max_failures=3)
    assert s.tick() == "healthy"  # learns the blend path
    h.fail = True
    s.tick()
    s.tick()
    assert s.tick() == "restarted"
    assert h.relaunches == 1
    assert h.restored == ["/tmp/hero.blend"]
    assert s.failures == 0
    assert s.restarts == 1


def test_restore_skipped_when_no_blend_was_ever_open() -> None:
    h = Harness({"bridge": "alive", "blend_path": ""})
    s = make(h, max_failures=1)
    assert s.tick() == "healthy"
    h.fail = True
    assert s.tick() == "restarted"
    assert h.relaunches == 1
    assert h.restored == []


def test_recovery_resets_the_failure_count() -> None:
    h = Harness()
    s = make(h, max_failures=3)
    h.fail = True
    s.tick()
    s.tick()
    h.fail = False
    assert s.tick() == "healthy"
    assert s.failures == 0


class BusyHarness:
    """A probe that answers with a structured timeout (socket alive, main thread busy on
    a legitimate heavy op) every single tick -- as would happen for the whole duration
    of a real 600s-tier operation."""

    def __init__(self) -> None:
        self.relaunches = 0
        self.restored: list[str] = []

    def probe(self) -> dict:
        raise BridgeError(TIMEOUT, "system.health exceeded 5.0s")

    def relaunch(self) -> None:
        self.relaunches += 1

    def restore(self, path: str) -> None:
        self.restored.append(path)


def test_busy_timeout_never_counts_toward_max_failures_or_relaunches() -> None:
    h = BusyHarness()
    s = Supervisor(probe=h.probe, relaunch=h.relaunch, restore=h.restore, max_failures=3)
    # Many more ticks than max_failures: a legitimate 600s-tier op at a 5s poll interval
    # blows through max_failures=3 dozens of times over -- must never relaunch.
    for _ in range(50):
        assert s.tick() == "busy"
    assert h.relaunches == 0
    assert s.failures == 0
    assert s.restarts == 0


def test_connection_error_still_relaunches_despite_busy_detection() -> None:
    """A transport/connection error (the socket never answered -- Blender is actually
    dead) is not a timeout code, so it must still count toward max_failures and trigger
    a relaunch, proving busy-detection doesn't swallow real dead-bridge failures."""
    h = Harness({"bridge": "alive", "blend_path": "/tmp/hero.blend"})
    s = make(h, max_failures=3)
    assert s.tick() == "healthy"

    def failing_probe():
        raise BridgeError(TRANSPORT, "cannot reach Blender bridge at 127.0.0.1:8765")

    s.probe = failing_probe
    assert s.tick() == "degraded"
    assert s.tick() == "degraded"
    assert s.tick() == "restarted"
    assert h.relaunches == 1


def test_relaunch_failure_is_swallowed_and_retried_next_tick() -> None:
    """A relaunch()/restore() exception inside tick() must not propagate -- it counts as
    a continued failure and the watchdog retries on the next tick."""
    h = Harness()
    calls = {"n": 0}

    def flaky_relaunch() -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("subprocess spawn failed")
        h.relaunches += 1
        h.fail = False  # the second relaunch attempt actually succeeds

    s = Supervisor(probe=h.probe, relaunch=flaky_relaunch, restore=h.restore, max_failures=1)
    h.fail = True

    # tick 1: crosses max_failures, attempts relaunch, relaunch raises -> swallowed.
    assert s.tick() == "degraded"
    assert s.restarts == 0
    assert h.relaunches == 0

    # tick 2: probe still fails (relaunch #1 never flipped h.fail), retries relaunch,
    # which succeeds this time.
    assert s.tick() == "restarted"
    assert s.restarts == 1
    assert h.relaunches == 1
