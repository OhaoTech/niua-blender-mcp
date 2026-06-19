"""Feedback: the agent's eyes.

Three read-only captures, all degrading gracefully (``available: false``) when no
GPU/display is available (pure headless), since visual feedback is a GUI-session feature
and analytic feedback covers headless:

* ``feedback.capture`` -- one image of a named view (or the live scene camera).
* ``feedback.capture_views`` -- a preset multi-angle set (the anti-blob: judge form from
  several angles, not one lucky shot).
* ``feedback.turntable`` -- an orbit around the object/scene.
* ``feedback.critique`` -- the one OBSERVE call the agent uses to *judge*: multi-angle
  images AND the analytic mesh/UV report in a single bundle, so the (multimodal) agent has
  both taste signal and checkable facts in one round-trip.

The rendering engine (dedicated hidden capture camera + framing math + workbench/EEVEE
opengl render) lives in ``..core.capture``; handlers stay tiny and never move the user's
viewport or view.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from .mesh import report as mesh_report
from .uv import report as uv_report


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


def critique(ctx: Ctx, payload: dict) -> dict:
    """The one observe call to judge a model: multi-angle images + analytic report.

    Bundles ``feedback.capture_views`` (taste signal -- the anti-blob) with ``mesh.report``
    (checkable facts) and, for a mesh, ``uv.report``. The agent is the critic: it reads the
    silhouette/proportion/topology from the images and the numbers, then keeps or reverts.
    Read-only; degrades to ``available: false`` images on a headless/no-GPU box while the
    analytic report still comes back.
    """
    from ..core import capture as cap

    obj = payload.get("object")
    preset = str(payload.get("preset", "ortho4"))
    shading = str(payload.get("shading", "SOLID"))
    res = int(payload.get("res", 640))

    views = cap.capture_views(ctx.bpy, preset=preset, shading=shading, res=res, obj_name=obj)

    report: dict[str, Any] | None = None
    uv: dict[str, Any] | None = None
    is_mesh = False
    try:
        report = mesh_report(ctx, {"object": obj} if obj else {})
        is_mesh = True
    except Exception as exc:  # noqa: BLE001 - non-mesh / no-object: report stays null
        report = {"available": False, "reason": str(exc)}
    if is_mesh:
        try:
            uv = uv_report(ctx, {"object": obj} if obj else {})
        except Exception:  # noqa: BLE001 - keep the bundle even if UV introspection trips
            uv = None

    return {
        "available": views.get("available", False),
        "images": views.get("images", []),
        "report": report,
        "uv": uv,
    }


COMMANDS = [
    Command("feedback.capture", capture, mutates=False),
    Command("feedback.capture_views", capture_views, mutates=False),
    Command("feedback.turntable", turntable, mutates=False),
    Command("feedback.critique", critique, mutates=False),
]
