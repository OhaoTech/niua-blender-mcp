"""Feedback: the agent's eyes.

`feedback.capture` renders the current view to a PNG and returns it base64-encoded so
a multimodal agent can see its work. It degrades gracefully (``available: false``) when
no GPU/display is available (e.g. pure headless), since visual feedback is a GUI-session
feature; analytic feedback covers headless.
"""

from __future__ import annotations

import base64
import os
import tempfile

from ..context import Ctx
from ..dispatch import Command


def capture(ctx: Ctx, payload: dict) -> dict:
    bpy = ctx.bpy
    mode = str(payload.get("mode", "viewport"))
    path = os.path.join(tempfile.gettempdir(), "niua_capture.png")
    try:
        scene = bpy.context.scene
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = path
        # Fast workbench/viewport render; full render is a later refinement.
        bpy.ops.render.opengl(write_still=True)
        with open(path, "rb") as handle:
            data = base64.b64encode(handle.read()).decode("ascii")
        return {"available": True, "mode": mode, "mimeType": "image/png", "encoding": "base64", "data": data}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract here
        return {"available": False, "mode": mode, "reason": str(exc)}


COMMANDS = [Command("feedback.capture", capture, mutates=False)]
