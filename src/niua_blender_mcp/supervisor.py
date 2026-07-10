"""Bridge watchdog: probe system.health, relaunch a dead Blender, restore the session.

Interface-layer (Part 1): knows sockets, processes, and .blend paths -- nothing about
assets or finishing. The state machine takes injected probe/relaunch/restore callables
so the offline suite exercises every transition without a Blender or a subprocess;
scripts/blender_supervise.py provides the real ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Supervisor:
    probe: Callable[[], dict[str, Any]]  # raises on failure (e.g. BridgeError)
    relaunch: Callable[[], None]
    restore: Callable[[str], None]
    max_failures: int = 3
    failures: int = field(default=0, init=False)
    restarts: int = field(default=0, init=False)
    last_blend_path: str = field(default="", init=False)

    def tick(self) -> str:
        """One watchdog cycle: 'healthy' | 'degraded' | 'restarted'."""
        try:
            health = self.probe()
        except Exception:  # noqa: BLE001 - any probe failure counts against the bridge
            self.failures += 1
            if self.failures < self.max_failures:
                return "degraded"
            self.relaunch()
            if self.last_blend_path:
                self.restore(self.last_blend_path)
            self.failures = 0
            self.restarts += 1
            return "restarted"
        self.failures = 0
        path = str(health.get("blend_path") or "")
        if path:
            self.last_blend_path = path
        return "healthy"
