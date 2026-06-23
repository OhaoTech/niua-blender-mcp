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
from ..core.orientation_metrics import orientation_quality
from ..dispatch import Command
from .mesh import (
    _bmesh_for,
    _resolve_mesh,
    bbox_dimensions,
    report as mesh_report,
    topology_counts,
    transform_applied,
)
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


def _loose_verts(bm: Any) -> int:
    """Verts with no linked edges (orphan geometry)."""
    return sum(1 for v in bm.verts if len(v.link_edges) == 0)


def _pole_count(bm: Any) -> int:
    """Interior verts whose edge valence != 4 (poles); boundary verts are excluded.

    A boundary vert (touching a non-manifold/border edge) naturally has valence != 4 and
    is not a topology defect, so it must not be counted as a pole.
    """
    poles = 0
    for v in bm.verts:
        if any(not e.is_manifold for e in v.link_edges):
            continue  # boundary / non-manifold vert: not a pole
        if len(v.link_edges) != 4:
            poles += 1
    return poles


def _topology_quality(obj: Any, counts: dict) -> dict:
    """Topology block: face-count metrics (always) + bmesh-derived metrics (or null)."""
    pole_count: int | None = None
    non_manifold_edges: int | None = None
    loose_verts: int | None = None
    bm = _bmesh_for(obj)
    if bm is not None:
        try:
            pole_count = _pole_count(bm)
            non_manifold_edges = sum(1 for e in bm.edges if not e.is_manifold)
            loose_verts = _loose_verts(bm)
        finally:
            bm.free()
    return {
        "faces": counts["faces"],
        "tris": counts["tris"],
        "quads": counts["quads"],
        "ngons": counts["ngons"],
        "quad_ratio": counts["quad_ratio"],
        "ngon_ratio": counts["ngon_ratio"],
        "pole_count": pole_count,
        "non_manifold_edges": non_manifold_edges,
        "loose_verts": loose_verts,
    }


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


def _scale(obj: Any) -> dict:
    return {
        "bbox_dimensions": bbox_dimensions(obj),
        "transform_applied": transform_applied(obj),
    }


def quality(ctx: Ctx, payload: dict) -> dict:
    """Objective quality metrics for a mesh: topology, UVs, orientation, symmetry, proportion, scale.

    The numeric judgment channel that complements the multi-angle images — so the agent's
    do->observe->judge->revert loop converges on facts, not vibes. Read-only; bmesh-derived
    fields (pole_count, non_manifold_edges, loose_verts) degrade to ``null`` without bmesh.
    """
    obj = _resolve_mesh(ctx, payload)
    mesh = obj.data
    counts = topology_counts(mesh)
    return {
        "object": obj.name,
        "topology": _topology_quality(obj, counts),
        "uv": uv_report(ctx, {"object": obj.name}),
        "orientation": orientation_quality(obj),
        "symmetry": _symmetry(mesh),
        "proportion": _proportion(obj),
        "scale": _scale(obj),
    }


def _quality_compact(ctx: Ctx, obj_name: Any) -> dict | None:
    """A compact quality sub-dict for folding into ``critique`` (best-effort, never raises)."""
    try:
        full = quality(ctx, {"object": obj_name} if obj_name else {})
    except Exception:  # noqa: BLE001 - non-mesh / no-object: critique stays usable
        return None
    topo = full["topology"]
    return {
        "quad_ratio": topo["quad_ratio"],
        "ngon_ratio": topo["ngon_ratio"],
        "pole_count": topo["pole_count"],
        "non_manifold_edges": topo["non_manifold_edges"],
        "loose_verts": topo["loose_verts"],
        "uv": full["uv"],
        "orientation": full["orientation"],
        "symmetry": full["symmetry"],
        "aspect_ratio": full["proportion"]["aspect_ratio"],
        "transform_applied": full["scale"]["transform_applied"],
    }


def critique(ctx: Ctx, payload: dict) -> dict:
    """The one observe call to judge a model: multi-angle images + analytic report.

    Bundles ``feedback.capture_views`` (taste signal -- the anti-blob) with ``mesh.report``
    (checkable facts), a compact ``quality`` sub-dict (the objective judgment channel:
    quad/n-gon ratios, poles, non-manifold, symmetry, aspect) and, for a mesh, ``uv.report``.
    The agent is the critic: it reads silhouette/proportion from the images and
    topology/symmetry/scale from the numbers, then keeps or reverts. Read-only; degrades to
    ``available: false`` images on a headless/no-GPU box while the analytic half still comes
    back.
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
        # Fold a compact objective-quality block into the report so one observe call gives
        # images + counts + quality.
        compact = _quality_compact(ctx, obj)
        if compact is not None:
            report["quality"] = compact
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
    Command("feedback.quality", quality, mutates=False),
]
