"""Godot round-trip verifier: unit tests fake the binary; one integration test uses a real godot."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from niua_blender_mcp.evals import godot_roundtrip as rt


def test_unavailable_without_godot_binary(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: None)
    out = rt.verify_gltf_import(str(glb))
    assert out == {"available": False, "reason": "godot binary not found: godot"}


def test_unavailable_without_export_file(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    out = rt.verify_gltf_import("/nope/missing.glb")
    assert out["available"] is False and "missing" in out["reason"]


def _fake_run(rc=0, out="", err="", make_artifacts=True):
    def run(cmd, capture_output, text, timeout):
        proj = cmd[cmd.index("--path") + 1]
        if make_artifacts:
            Path(proj, "asset.glb.import").write_text("[remap]")
            imported = Path(proj, ".godot", "imported")
            imported.mkdir(parents=True)
            (imported / "asset.glb-abc123.scn").write_bytes(b"scn")
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)
    return run


def test_clean_import_is_ok(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    monkeypatch.setattr(subprocess, "run", _fake_run(rc=0, out="importing asset.glb\n"))
    out = rt.verify_gltf_import(str(glb))
    assert out["available"] is True and out["ok"] is True
    assert out["errors"] == [] and out["sidecar"] is True


def test_error_lines_fail_the_import(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    monkeypatch.setattr(subprocess, "run",
                        _fake_run(rc=0, err="ERROR: glTF: buffer overrun in asset.glb\n"))
    out = rt.verify_gltf_import(str(glb))
    assert out["ok"] is False and any("buffer overrun" in e for e in out["errors"])


def test_missing_artifacts_fail_the_import(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")
    monkeypatch.setattr(subprocess, "run", _fake_run(rc=0, make_artifacts=False))
    out = rt.verify_gltf_import(str(glb))
    assert out["ok"] is False


def test_timeout_is_a_measured_failure(tmp_path, monkeypatch):
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/godot")

    def boom(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)
    monkeypatch.setattr(subprocess, "run", boom)
    out = rt.verify_gltf_import(str(glb), timeout=5)
    assert out["available"] is True and out["ok"] is False
    assert any("timed out" in e for e in out["errors"])


_FIXTURES = Path(__file__).resolve().parents[2] / "src/niua_blender_mcp/evals/benchmark/assets"


@pytest.mark.skipif(shutil.which("godot") is None, reason="no godot binary")
@pytest.mark.skipif(not any(_FIXTURES.glob("*.glb")) if _FIXTURES.is_dir() else True,
                    reason="no local .glb fixture (git-ignored)")
def test_real_godot_imports_a_real_fixture():
    # Smallest fixture by file size (not alphabetical) — import time matters,
    # and fixtures range up to ~60MB/978k tris.
    glb = min(_FIXTURES.glob("*.glb"), key=lambda p: p.stat().st_size)
    out = rt.verify_gltf_import(str(glb), timeout=300)
    assert out["available"] is True
    assert out["ok"] is True, out  # a known-good generator asset must import clean
