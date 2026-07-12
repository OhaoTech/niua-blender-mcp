"""Godot round-trip import gate: the apex ground truth for "game-ready".

Shells out to a generic `godot` binary (any 4.x) with --headless --import on a
throwaway one-file project containing just the exported .glb. Standalone by design:
no engine-project knowledge, no MCP dependency — the only question answered is
"does this export import clean?" Degrades honestly: no godot binary or no export
file -> {"available": False} (UNMEASURED, never a fake pass or fail); a hung or
erroring import -> {"available": True, "ok": False} (a measured failure).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

_PROJECT_GODOT = 'config_version=5\n\n[application]\nconfig/name="niua_roundtrip"\n'


def verify_gltf_import(glb_path: str, godot_bin: str = "godot", timeout: float = 240.0) -> dict:
    if shutil.which(godot_bin) is None:
        return {"available": False, "reason": f"godot binary not found: {godot_bin}"}
    if not os.path.isfile(glb_path):
        return {"available": False, "reason": f"export file missing: {glb_path}"}
    with tempfile.TemporaryDirectory(prefix="niua_godot_rt_") as proj:
        with open(os.path.join(proj, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write(_PROJECT_GODOT)
        asset = os.path.join(proj, "asset.glb")
        shutil.copyfile(glb_path, asset)
        try:
            run = subprocess.run(
                [godot_bin, "--headless", "--path", proj, "--import"],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"available": True, "ok": False, "returncode": None,
                    "errors": [f"import timed out after {timeout:.0f}s"],
                    "sidecar": False, "artifacts": [], "log_tail": []}
        log = (run.stdout or "") + "\n" + (run.stderr or "")
        lines = [line.strip() for line in log.splitlines() if line.strip()]
        errors = [line for line in lines if line.startswith("ERROR") or "SCRIPT ERROR" in line]
        sidecar = os.path.isfile(asset + ".import")
        imported_dir = os.path.join(proj, ".godot", "imported")
        artifacts = sorted(os.listdir(imported_dir)) if os.path.isdir(imported_dir) else []
        ok = (run.returncode == 0 and not errors and sidecar
              and any(a.startswith("asset.glb") for a in artifacts))
        return {"available": True, "ok": ok, "returncode": run.returncode,
                "errors": errors[:10], "sidecar": sidecar,
                "artifacts": artifacts[:10], "log_tail": lines[-5:]}
