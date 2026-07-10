"""Supervisor state machine: probe -> degraded -> relaunch + session restore."""

from __future__ import annotations

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
