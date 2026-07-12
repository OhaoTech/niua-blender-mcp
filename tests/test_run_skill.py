"""Offline guards for the code-mode skill runner."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _load_runner():
    sys.path.insert(0, str(_REPO / "scripts"))
    import run_skill  # noqa: E402
    return run_skill


def test_runner_parses():
    import ast
    ast.parse((_REPO / "scripts" / "run_skill.py").read_text(encoding="utf-8"))


def test_recording_session_records_calls():
    runner = _load_runner()

    class _Bridge:
        def call(self, command, args):
            return {"echo": command}

    session = runner.RecordingSession(_Bridge())
    session.mesh.select_all(object="Cube", action="SELECT")
    assert session.recorded == [
        {"tool": "mesh.select_all", "arguments": {"object": "Cube", "action": "SELECT"},
         "result": {"echo": "mesh.select_all"}}
    ]


def test_skill_tools_used_are_registered():
    runner = _load_runner()
    from niua_blender_mcp.finishing.skills.make_game_ready import TOOLS_USED
    assert TOOLS_USED <= runner.known_tools()
