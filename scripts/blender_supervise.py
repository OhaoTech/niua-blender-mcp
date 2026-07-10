#!/usr/bin/env python3
"""Self-healing Blender launcher: one command that starts a visible Blender with the
bridge, then watchdogs it -- dead bridge => kill + relaunch => reopen the last .blend.

    python scripts/blender_supervise.py [--port 8765] [--blender blender] \
        [--addon-dir <repo>/blender_addon] [--interval 5] [--max-failures 3]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from niua_blender_mcp.bridge import BlenderBridge  # noqa: E402
from niua_blender_mcp.supervisor import Supervisor  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BlenderProcess:
    """Owns the Blender subprocess: launch via scripts/blender_gui.py, wait for the bridge."""

    def __init__(self, blender: str, addon_dir: str, port: int) -> None:
        self.blender = blender
        self.addon_dir = addon_dir
        self.port = port
        self.proc: subprocess.Popen | None = None

    def launch(self) -> None:
        self.terminate()
        gui = os.path.join(REPO, "scripts", "blender_gui.py")
        self.proc = subprocess.Popen(  # noqa: S603 - trusted local dev launcher
            [self.blender, "--python", gui, "--", self.addon_dir, str(self.port)]
        )
        self._wait_for_bridge()

    def terminate(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()  # reap the zombie; kill() alone doesn't block for exit
        self.proc = None

    def _wait_for_bridge(self, attempts: int = 60) -> None:
        bridge = BlenderBridge(port=self.port)
        for _ in range(attempts):
            try:
                bridge.call("system.health", {}, timeout=5.0)
                return
            except Exception:  # noqa: BLE001 - bridge not up yet
                time.sleep(1.0)
        raise RuntimeError(f"bridge did not come up on port {self.port}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Self-healing Blender bridge supervisor.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--addon-dir", default=os.path.join(REPO, "blender_addon"))
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--max-failures", type=int, default=3)
    args = ap.parse_args(argv)

    bridge = BlenderBridge(port=args.port)
    process = BlenderProcess(args.blender, args.addon_dir, args.port)

    def restore(path: str) -> None:
        # Reopen the last session via the generic RNA passthrough (no dedicated tool needed).
        bridge.call(
            "capabilities.invoke",
            {"idname": "wm.open_mainfile", "args": json.dumps({"filepath": path})},
            timeout=60.0,
        )

    supervisor = Supervisor(
        probe=lambda: bridge.call("system.health", {}, timeout=5.0),
        relaunch=process.launch,
        restore=restore,
        max_failures=args.max_failures,
    )

    process.launch()
    print(f"[niua-supervise] watching bridge on 127.0.0.1:{args.port}", flush=True)
    try:
        while True:
            try:
                state = supervisor.tick()
            except Exception as exc:  # noqa: BLE001 - the watchdog itself must never die
                print(f"[niua-supervise] tick failed: {exc!r}", file=sys.stderr, flush=True)
                time.sleep(args.interval)
                continue
            if state != "healthy":
                print(f"[niua-supervise] {state} (restarts={supervisor.restarts})", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        process.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
