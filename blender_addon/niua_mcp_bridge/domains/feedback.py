"""Feedback: the agent's generic eyes (interface layer).

Four read-only captures, all degrading gracefully (``available: false``) when no
GPU/display is available (pure headless), since visual feedback is a GUI-session feature:

* ``feedback.capture`` -- one image of a named view (or the live scene camera).
* ``feedback.capture_views`` -- a preset multi-angle set (the anti-blob: judge form from
  several angles, not one lucky shot).
* ``feedback.turntable`` -- an orbit around the object/scene.
* ``feedback.silhouette`` -- a single-view alpha silhouette + pure-geometry proportion/
  symmetry read, no policy judgment attached.

The rendering engine (dedicated hidden capture camera + framing math + workbench/EEVEE
opengl render) lives in ``..core.capture``; handlers stay tiny and never move the user's
viewport or view.

The policy-laden judgment tools that used to live here (``feedback.quality``,
``feedback.critique``, ``feedback.capture_intake``, ``feedback.preservation``,
``feedback.readiness``) moved to ``domains/finishing_feedback.py`` -- this module must
never import from ``..finishing``. ``_proportion``/``_symmetry`` below are pure-geometry
helpers shared by both layers: ``feedback.silhouette`` here and ``feedback.quality`` in
finishing_feedback both use them, so they stay interface and finishing imports them
(that direction is allowed).
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from .mesh import bbox_dimensions


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


def silhouette(ctx: Ctx, payload: dict) -> dict:
    from ..core import silhouette as sil

    obj_name = payload.get("object")
    preset = str(payload.get("preset", "ortho4"))
    res = int(payload.get("res", 768))
    out = sil.render_silhouette(ctx.bpy, obj_name, preset=preset, res=res)
    if out.get("available"):
        obj = ctx.bpy.data.objects.get(obj_name) if obj_name else sil._active_mesh(ctx.bpy)
        if obj is not None and getattr(obj, "type", None) == "MESH":
            out["proportion"] = _proportion(obj)
            out["symmetry"] = _symmetry(obj.data)
    return out


def turntable(ctx: Ctx, payload: dict) -> dict:
    from ..core import capture as cap

    count = int(payload.get("count", 6))
    shading = str(payload.get("shading", "SOLID"))
    res = int(payload.get("res", 768))
    obj = payload.get("object")
    return cap.turntable(ctx.bpy, count=count, shading=shading, res=res, obj_name=obj)


def _local_coords(mesh: Any) -> list[tuple[float, float, float]]:
    """Object-local vertex coordinates as plain tuples (pure geometry, no bpy types)."""
    coords: list[tuple[float, float, float]] = []
    for v in getattr(mesh, "vertices", []) or []:
        co = getattr(v, "co", None)
        if co is None:
            continue
        coords.append((float(co[0]), float(co[1]), float(co[2])))
    return coords


def _symmetry_fraction(coords: list[tuple[float, float, float]], axis: int, eps: float) -> float | None:
    """Fraction of verts that have a mirror partner across the local plane normal to ``axis``.

    For axis=0 (X) the mirror plane is the local YZ plane: a vert ``p`` is symmetric if some
    vert sits near ``p`` with its ``axis`` coordinate negated. Pure geometry, no GPU. Verts
    already on the plane (coord ~ 0) count as self-symmetric. Returns ``None`` when there are
    no vertex coordinates to judge.
    """
    if not coords:
        return None
    # Bucket candidates by the two in-plane coordinates (rounded to the epsilon grid) so the
    # match is near-linear instead of O(n^2).
    others = [i for i in range(3) if i != axis]

    def key(p: tuple[float, float, float]) -> tuple[int, int]:
        return (round(p[others[0]] / eps), round(p[others[1]] / eps))

    buckets: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
    for p in coords:
        buckets.setdefault(key(p), []).append(p)

    matched = 0
    for p in coords:
        target = list(p)
        target[axis] = -p[axis]
        tkey = key(p)  # in-plane coords are unchanged by the mirror
        found = False
        for q in buckets.get(tkey, ()):  # noqa: B007
            if (
                abs(q[axis] - target[axis]) <= eps
                and abs(q[others[0]] - p[others[0]]) <= eps
                and abs(q[others[1]] - p[others[1]]) <= eps
            ):
                found = True
                break
        if found:
            matched += 1
    return matched / len(coords)


def _symmetry(mesh: Any, eps: float = 1e-4) -> dict:
    coords = _local_coords(mesh)
    return {
        "symmetry_x": _symmetry_fraction(coords, 0, eps),
        "symmetry_y": _symmetry_fraction(coords, 1, eps),
        "symmetry_z": _symmetry_fraction(coords, 2, eps),
    }


def _proportion(obj: Any) -> dict:
    dims = bbox_dimensions(obj)
    if not dims or all(d == 0 for d in dims):
        return {
            "bbox_dimensions": dims,
            "aspect_ratio": None,
            "boxiness": None,
        }
    positive = [d for d in dims if d > 0]
    longest = max(dims)
    shortest = min(positive) if positive else 0.0
    aspect = (longest / shortest) if shortest > 0 else None
    # boxiness hint: bbox volume / how "filled" it is by the longest^3 cube — cheap, no mesh.
    x, y, z = dims
    bbox_volume = x * y * z
    boxiness = (bbox_volume / (longest ** 3)) if longest > 0 else None
    return {
        "bbox_dimensions": dims,
        "aspect_ratio": aspect,
        "boxiness": boxiness,
    }


COMMANDS = [
    Command("feedback.capture", capture, mutates=False),
    Command("feedback.capture_views", capture_views, mutates=False),
    Command("feedback.silhouette", silhouette, mutates=False),
    Command("feedback.turntable", turntable, mutates=False),
]
