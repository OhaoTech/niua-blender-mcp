"""Feedback: the agent's eyes.

Three read-only captures, all degrading gracefully (``available: false``) when no
GPU/display is available (pure headless), since visual feedback is a GUI-session feature
and analytic feedback covers headless:

* ``feedback.capture`` -- one image of a named view (or the live scene camera).
* ``feedback.capture_views`` -- a preset multi-angle set (the anti-blob: judge form from
  several angles, not one lucky shot).
* ``feedback.turntable`` -- an orbit around the object/scene.

The rendering engine (dedicated hidden capture camera + framing math + workbench/EEVEE
opengl render) lives in ``..core.capture``; handlers stay tiny and never move the user's
viewport or view.
"""

from __future__ import annotations

from ..context import Ctx
from ..dispatch import Command


def capture(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap

    view = str(payload.get("view", "current"))
    shading = str(payload.get("shading", "SOLID"))
    res = int(payload.get("res", 768))
    obj = payload.get("object")
    return cap.render(ctx.bpy, view=view, shading=shading, res=res, obj_name=obj)


def capture_views(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap

    preset = str(payload.get("preset", "ortho4"))
    shading = str(payload.get("shading", "SOLID"))
    res = int(payload.get("res", 768))
    obj = payload.get("object")
    return cap.capture_views(ctx.bpy, preset=preset, shading=shading, res=res, obj_name=obj)


def turntable(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap

    count = int(payload.get("count", 6))
    shading = str(payload.get("shading", "SOLID"))
    res = int(payload.get("res", 768))
    obj = payload.get("object")
    return cap.turntable(ctx.bpy, count=count, shading=shading, res=res, obj_name=obj)


COMMANDS = [
    Command("feedback.capture", capture, mutates=False),
    Command("feedback.capture_views", capture_views, mutates=False),
    Command("feedback.turntable", turntable, mutates=False),
]
