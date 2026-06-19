"""End-to-end smoke test against a real headless Blender.

Launches `blender --background` running the bridge, then drives it through the same
BlenderBridge the MCP server uses. Skipped automatically when no blender binary is
available or NIUA_SKIP_BLENDER is set.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from niua_blender_mcp.bridge import BlenderBridge

REPO = Path(__file__).resolve().parents[1]
ADDON_DIR = REPO / "blender_addon"
LAUNCHER = REPO / "scripts" / "blender_serve.py"

BLENDER = os.environ.get("NIUA_BLENDER_BIN") or shutil.which("blender")

pytestmark = pytest.mark.skipif(
    not BLENDER or os.environ.get("NIUA_SKIP_BLENDER"),
    reason="blender binary not available (set NIUA_BLENDER_BIN or install blender)",
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"blender exited early with code {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError("blender bridge did not open the port in time")


@pytest.fixture()
def bridge():
    port = _free_port()
    proc = subprocess.Popen(
        [
            BLENDER, "--background", "--factory-startup",
            "--python", str(LAUNCHER), "--",
            str(ADDON_DIR), str(port), "0", "20",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_port(port, proc)
        yield BlenderBridge(port=port, timeout=30.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_scene_info_round_trips(bridge: BlenderBridge) -> None:
    info = bridge.call("scene.info", {})
    assert "objects" in info
    assert isinstance(info["objects"], list)


def test_create_move_and_undo_semantics(bridge: BlenderBridge) -> None:
    created = bridge.call("scene.create_object", {"type": "CUBE", "name": "NiuaHero"})
    assert created["name"] == "NiuaHero"

    moved = bridge.call("scene.set_transform", {"object": "NiuaHero", "location": [1, 2, 3]})
    assert moved["location"] == [1.0, 2.0, 3.0]

    info = bridge.call("scene.info", {})
    assert any(o["name"] == "NiuaHero" for o in info["objects"])


def test_rna_describe_reads_live_api(bridge: BlenderBridge) -> None:
    described = bridge.call("rna.describe", {"path": "op:mesh.primitive_cube_add"})
    assert described["kind"] == "operator"
    assert isinstance(described["properties"], list)


def test_set_transform_missing_object_is_clean_error(bridge: BlenderBridge) -> None:
    from niua_blender_mcp.bridge import BridgeError

    with pytest.raises(BridgeError) as exc:
        bridge.call("scene.set_transform", {"object": "DoesNotExist", "location": [0, 0, 0]})
    assert exc.value.code == "not_found"  # Blender survived; clean structured error


def test_failed_call_does_not_undo_prior_work(bridge: BlenderBridge) -> None:
    # Regression: a failed mutation must not revert the previous legitimate operation.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "KeepA"})
    from niua_blender_mcp.bridge import BridgeError

    with pytest.raises(BridgeError):
        bridge.call("scene.set_transform", {"object": "Ghost", "location": [0, 0, 0]})
    bridge.call("scene.create_object", {"type": "SPHERE", "name": "KeepB"})

    names = {o["name"] for o in bridge.call("scene.info", {})["objects"]}
    assert {"KeepA", "KeepB"} <= names  # neither was clobbered by the failed call


def test_mesh_edit_changes_geometry_end_to_end(bridge: BlenderBridge) -> None:
    # Full mesh pipeline in real Blender: create -> edit-mode op -> analytic report.
    # The kernel must guarantee EDIT mode + active mesh + selection (headless, no
    # VIEW_3D area), run one undoable mutation, and the geometry counts must change.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "MeshHero"})

    before = bridge.call("mesh.report", {"object": "MeshHero"})
    assert before["vertices"] == 8 and before["edges"] == 12 and before["faces"] == 6

    bridge.call("mesh.subdivide", {"object": "MeshHero", "cuts": 2})

    after = bridge.call("mesh.report", {"object": "MeshHero"})
    # A 2-cut subdivide turns each of the 6 cube faces into a 3x3 grid: 56v/108e/54f.
    assert after["vertices"] == 56
    assert after["edges"] == 108
    assert after["faces"] == 54
    # Strictly more geometry than before, and the edit was actually applied.
    assert after["vertices"] > before["vertices"]
    assert after["faces"] > before["faces"]
    assert after["ngons"] == 0


def test_feedback_capture_returns_a_verdict(bridge: BlenderBridge) -> None:
    # Headless has no GPU/display, so this may report unavailable; it must not crash.
    result = bridge.call("feedback.capture", {"mode": "viewport"})
    assert "available" in result
