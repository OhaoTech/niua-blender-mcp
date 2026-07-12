"""Bridge watchdog: probe system.health, relaunch a dead Blender, restore the session.

Interface-layer (Part 1): knows sockets, processes, and .blend paths -- nothing about
assets or finishing. The state machine takes injected probe/relaunch/restore callables
so the offline suite exercises every transition without a Blender or a subprocess;
scripts/blender_supervise.py provides the real ones.

Busy-vs-dead: a probe failure whose exception carries ``code == "timeout"`` (duck-typed,
so this module never has to import BridgeError) means the socket answered and the
process is alive -- it's just busy behind a legitimate heavy op. That must never count
toward max_failures, or the supervisor would relaunch Blender mid-operation.
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
        """One watchdog cycle: 'healthy' | 'busy' | 'degraded' | 'restarted'."""
        try:
            health = self.probe()
        except Exception as exc:  # noqa: BLE001 - any probe failure counts against the bridge
            if getattr(exc, "code", None) == "timeout":
                # The socket answered with a structured timeout: the add-on enqueued the
                # probe and the main thread is busy on a legitimate heavy op, but the
                # process itself is alive. Only transport/connection errors (the socket
                # never answered at all) count toward max_failures -- a busy-but-alive
                # Blender must never get killed mid-op.
                return "busy"
            self.failures += 1
            if self.failures < self.max_failures:
                return "degraded"
            try:
                self.relaunch()
                if self.last_blend_path:
                    self.restore(self.last_blend_path)
            except Exception:  # noqa: BLE001 - relaunch/restore failing must not crash the watchdog
                return "degraded"
            self.failures = 0
            self.restarts += 1
            return "restarted"
        self.failures = 0
        path = str(health.get("blend_path") or "")
        if path:
            self.last_blend_path = path
        return "healthy"
