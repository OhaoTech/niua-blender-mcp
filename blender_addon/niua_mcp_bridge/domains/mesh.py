"""Mesh domain handlers: extrude, bevel, inset, subdivide, normals, shading, report.

Handlers stay tiny: the kernel does validation, undo and (for edit ops) context.
Edit-mode operators are wrapped in ``ctx.ensure(active=obj, mode="EDIT", select=[obj])``
so the active object, selection and interaction mode are guaranteed and restored; a
failing ``poll()`` is surfaced as a clean ``precondition_failed`` via ``ctx.check_poll``.
``mesh.report`` is read-only analytic feedback.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import PRECONDITION, BridgeError


def _resolve_mesh(ctx: Ctx, payload: dict) -> Any:
    """Return the target mesh object (named, else active); fail cleanly otherwise."""
    name = payload.get("object")
    if isinstance(name, str) and name:
        obj = ctx.get_object(name)
    else:
        view_layer = getattr(ctx.bpy.context, "view_layer", None)
        obj = getattr(getattr(view_layer, "objects", None), "active", None)
        if obj is None:
            obj = getattr(ctx.bpy.context, "object", None)
        if obj is None:
            raise BridgeError(PRECONDITION, "no active object; pass 'object'")
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(
            PRECONDITION,
            f"object is not a mesh: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    return obj


def _edit(ctx: Ctx, obj: Any, op: Any, **kwargs: Any) -> None:
    """Run an edit-mode operator with guaranteed context and a clean precondition error."""
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(op)
        op(**kwargs)


def extrude(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    translate = payload.get("translate") or [0.0, 0.0, 0.0]
    op = ctx.bpy.ops.mesh.extrude_region_move
    _edit(
        ctx,
        obj,
        op,
        TRANSFORM_OT_translate={"value": tuple(float(v) for v in translate)},
    )
    return {"object": obj.name, "extruded": True, "translate": [float(v) for v in translate]}


def bevel(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    offset = float(payload.get("offset", 0.1))
    segments = int(payload.get("segments", 1))
    _edit(ctx, obj, ctx.bpy.ops.mesh.bevel, offset=offset, segments=segments)
    return {"object": obj.name, "offset": offset, "segments": segments}


def inset(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    thickness = float(payload.get("thickness", 0.1))
    _edit(ctx, obj, ctx.bpy.ops.mesh.inset, thickness=thickness)
    return {"object": obj.name, "thickness": thickness}


def subdivide(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    cuts = int(payload.get("cuts", 1))
    _edit(ctx, obj, ctx.bpy.ops.mesh.subdivide, number_cuts=cuts)
    return {"object": obj.name, "cuts": cuts}


def recalc_normals(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    inside = bool(payload.get("inside", False))
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ctx.bpy.ops.mesh.select_all)
        ctx.bpy.ops.mesh.select_all(action="SELECT")
        ctx.check_poll(ctx.bpy.ops.mesh.normals_make_consistent)
        ctx.bpy.ops.mesh.normals_make_consistent(inside=inside)
    return {"object": obj.name, "inside": inside}


def _selected_indices(items: Any) -> list[int]:
    out: list[int] = []
    for fallback, item in enumerate(list(items or [])):
        if bool(getattr(item, "select", False)):
            out.append(int(getattr(item, "index", fallback)))
    return out


def _selection_report(obj: Any) -> dict:
    mesh = getattr(obj, "data", None)
    vertices = _selected_indices(getattr(mesh, "vertices", []))
    edges = _selected_indices(getattr(mesh, "edges", []))
    faces = _selected_indices(getattr(mesh, "polygons", []))
    return {
        "object": getattr(obj, "name", ""),
        "vertices": vertices,
        "edges": edges,
        "faces": faces,
        "counts": {"vertices": len(vertices), "edges": len(edges), "faces": len(faces)},
    }


def selection_report(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        return _selection_report(obj)


def select_all(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    action = str(payload.get("action", "SELECT"))
    _edit(ctx, obj, ctx.bpy.ops.mesh.select_all, action=action)
    return {"object": obj.name, "action": action}


def shade_smooth(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    smooth = bool(payload.get("smooth", True))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        if smooth:
            ctx.check_poll(ctx.bpy.ops.object.shade_smooth)
            ctx.bpy.ops.object.shade_smooth()
        else:
            ctx.check_poll(ctx.bpy.ops.object.shade_flat)
            ctx.bpy.ops.object.shade_flat()
    return {"object": obj.name, "smooth": smooth}


def _bmesh_for(obj: Any) -> Any | None:
    """Build a fresh bmesh from an object's mesh data, or None when bmesh is unavailable.

    Caller owns the returned bmesh and MUST ``free()`` it. ``None`` lets callers degrade
    metric fields gracefully (fake-bpy / partial envs have no ``bmesh``).
    """
    try:
        import bmesh  # noqa: PLC0415 - optional; only present inside Blender
    except Exception:  # noqa: BLE001 - fake-bpy / partial envs lack bmesh
        return None
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
    except Exception:  # noqa: BLE001 - degrade rather than crash dispatch
        bm.free()
        return None
    return bm


def _non_manifold_edges(obj: Any) -> int | None:
    """Count non-manifold edges via bmesh if importable; else None."""
    bm = _bmesh_for(obj)
    if bm is None:
        return None
    try:
        return sum(1 for e in bm.edges if not e.is_manifold)
    finally:
        bm.free()


def topology_counts(mesh: Any) -> dict:
    """Pure face-count topology from mesh ``polygons`` (no bmesh): the shared core of
    ``mesh.report`` and ``feedback.quality``. Counts faces, triangulated tris, quads and
    n-gons plus the quad/n-gon ratios.
    """
    polygons = list(getattr(mesh, "polygons", []) or [])
    faces = len(polygons)
    triangles = 0
    quads = 0
    ngons = 0
    for poly in polygons:
        count = len(getattr(poly, "vertices", []) or [])
        triangles += max(count - 2, 0)
        if count == 4:
            quads += 1
        elif count > 4:
            ngons += 1
    return {
        "faces": faces,
        "tris": triangles,
        "quads": quads,
        "ngons": ngons,
        "quad_ratio": (quads / faces) if faces else 0.0,
        "ngon_ratio": (ngons / faces) if faces else 0.0,
    }


def bbox_dimensions(obj: Any) -> list[float] | None:
    dims = getattr(obj, "dimensions", None)
    return [float(v) for v in dims] if dims is not None else None


def transform_applied(obj: Any) -> bool:
    matrix = getattr(obj, "matrix_world", None)
    return _is_identity(matrix) if matrix is not None else False


def report(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    mesh = obj.data
    counts = topology_counts(mesh)
    vertices = list(getattr(mesh, "vertices", []) or [])
    edges = list(getattr(mesh, "edges", []) or [])

    return {
        "object": obj.name,
        "vertices": len(vertices),
        "edges": len(edges),
        "faces": counts["faces"],
        "triangles": counts["tris"],
        "ngons": counts["ngons"],
        "non_manifold_edges": _non_manifold_edges(obj),
        "bbox_dimensions": bbox_dimensions(obj),
        "uv_layers": len(getattr(mesh, "uv_layers", []) or []),
        "materials": len(getattr(mesh, "materials", []) or []),
        "transform_applied": transform_applied(obj),
    }


def _is_identity(matrix: Any) -> bool:
    """True if a 4x4 matrix is (close to) the identity, i.e. transform is applied."""
    try:
        rows = [list(row) for row in matrix]
    except TypeError:
        return False
    if len(rows) != 4:
        return False
    for i, row in enumerate(rows):
        if len(row) != 4:
            return False
        for j, value in enumerate(row):
            expected = 1.0 if i == j else 0.0
            if abs(float(value) - expected) > 1e-6:
                return False
    return True


COMMANDS = [
    Command("mesh.extrude", extrude, mutates=True, feedback="viewport"),
    Command("mesh.bevel", bevel, mutates=True, feedback="viewport"),
    Command("mesh.inset", inset, mutates=True, feedback="viewport"),
    Command("mesh.subdivide", subdivide, mutates=True, feedback="viewport"),
    Command("mesh.recalc_normals", recalc_normals, mutates=True, feedback="viewport"),
    Command("mesh.selection_report", selection_report, mutates=False),
    Command("mesh.select_all", select_all, mutates=True, feedback="viewport"),
    Command("mesh.shade_smooth", shade_smooth, mutates=True, feedback="viewport"),
    Command("mesh.report", report, mutates=False),
]
