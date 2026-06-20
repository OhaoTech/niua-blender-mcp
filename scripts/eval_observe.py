"""Deterministic observe+score step for the Phase-B convergence loop.

Given a live bridge port, a battery task id, and the subject object name, this:
  1. reads objective metrics via feedback.quality,
  2. checks them against the task's gates (the un-gameable signal),
  3. saves the eye renders (feedback.topology + multi-angle) to an output dir for
     the multimodal judge to look at (best-effort; degrades on headless/no-GL),
  4. prints a scorecard JSON: {task, subject, gates, gates_pass, images, available}.

Scoring lives HERE (Python), never in an agent, so the loop cannot be talked into
a passing score. The judge (taste) is a separate, later step in the workflow.
"""

from __future__ import annotations

import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from niua_blender_mcp.bridge import BlenderBridge, BridgeError  # noqa: E402
from niua_blender_mcp.evals.battery import load_task  # noqa: E402
from niua_blender_mcp.evals.gates import check_gates  # noqa: E402


def _save_images(envelope: dict, outdir: str, prefix: str) -> list[str]:
    paths: list[str] = []
    imgs = envelope.get("images") or ([envelope] if envelope.get("data") else [])
    for i, img in enumerate(imgs):
        data = img.get("data")
        if not data:
            continue
        tag = img.get("mode") or img.get("view") or str(i)
        path = os.path.join(outdir, f"{prefix}_{tag}.png")
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data))
        paths.append(path)
    return paths


def main(argv: list[str]) -> int:
    port = int(argv[1])
    task_id = argv[2]
    subject = argv[3] if len(argv) > 3 else "Subject"
    outdir = argv[4] if len(argv) > 4 else "/tmp/niua_eval"
    os.makedirs(outdir, exist_ok=True)

    b = BlenderBridge(port=port, timeout=120.0)
    task = load_task(task_id)

    try:
        metrics = b.call("feedback.quality", {"object": subject})
    except BridgeError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message}}))
        return 1

    gate = check_gates(metrics, task["gates"])

    images: list[str] = []
    available = False
    try:
        topo = b.call("feedback.topology", {"object": subject, "view": "persp", "res": 512})
        if topo.get("available"):
            available = True
            images += _save_images(topo, outdir, "topo")
        views = b.call("feedback.capture_views", {"object": subject, "preset": "ortho4", "res": 512})
        if views.get("available"):
            available = True
            images += _save_images(views, outdir, "view")
    except BridgeError:
        pass  # eyes are best-effort; gates already carry the objective signal

    print(json.dumps({
        "task": task_id,
        "subject": subject,
        "metrics": metrics,
        "gates": gate["gates"],
        "gates_pass": gate["gates_pass"],
        "judge_threshold": task["judge_threshold"],
        "images": images,
        "images_available": available,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
