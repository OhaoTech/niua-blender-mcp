"""UV domain handlers: unwrapping, projection, island layout, report.

Handlers stay tiny: the kernel does validation, undo and (for edit ops) context.
All projection/unwrap operators run in EDIT mode wrapped in
``ctx.ensure(active=obj, mode="EDIT", select=[obj])`` so the active object, selection
and interaction mode are guaranteed and restored; a failing ``poll()`` surfaces as a
clean ``precondition_failed`` via ``ctx.check_poll``. Each op selects all faces first so
the projection/pack covers the whole mesh, not a stale sub-selection. ``uv.report`` is
read-only analytic feedback.
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


def _edit_all_faces(ctx: Ctx, obj: Any, op: Any, **kwargs: Any) -> None:
    """Enter EDIT mode, select every face, then run a UV operator with a clean error.

    UV projection/unwrap operators act on the *selected* faces. We select all faces so
    the result covers the whole mesh; without this an unrelated stale selection would
    silently leave most faces unmapped.
    """
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ctx.bpy.ops.mesh.select_all)
        ctx.bpy.ops.mesh.select_all(action="SELECT")
        ctx.check_poll(op)
        op(**kwargs)


def smart_unwrap(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    angle_limit = float(payload.get("angle_limit", 66.0))
    island_margin = float(payload.get("island_margin", 0.0))
    _edit_all_faces(
        ctx,
        obj,
        ctx.bpy.ops.uv.smart_project,
        angle_limit=angle_limit,
        island_margin=island_margin,
    )
    return {"object": obj.name, "angle_limit": angle_limit, "island_margin": island_margin}


def unwrap(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    method = str(payload.get("method", "ANGLE_BASED"))
    island_margin = float(payload.get("island_margin", 0.0))
    _edit_all_faces(
        ctx,
        obj,
        ctx.bpy.ops.uv.unwrap,
        method=method,
        margin=island_margin,
    )
    return {"object": obj.name, "method": method, "island_margin": island_margin}


def cube_project(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    cube_size = float(payload.get("cube_size", 1.0))
    _edit_all_faces(ctx, obj, ctx.bpy.ops.uv.cube_project, cube_size=cube_size)
    return {"object": obj.name, "cube_size": cube_size}


def sphere_project(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    _edit_all_faces(ctx, obj, ctx.bpy.ops.uv.sphere_project)
    return {"object": obj.name, "projected": True}


def pack_islands(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    margin = float(payload.get("margin", 0.001))
    _edit_all_faces(ctx, obj, ctx.bpy.ops.uv.pack_islands, margin=margin)
    return {"object": obj.name, "margin": margin}


def average_islands_scale(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    _edit_all_faces(ctx, obj, ctx.bpy.ops.uv.average_islands_scale)
    return {"object": obj.name, "averaged": True}


def _island_count(obj: Any) -> int | None:
    """Count UV islands via bmesh if importable; else None.

    Islands are connected components of faces sharing UV-coincident loop corners. We
    union-find faces that share an edge whose two loops have matching UVs on both sides
    (i.e. the seam is *not* split in UV space).
    """
    try:
        import bmesh  # noqa: PLC0415 - optional; only present inside Blender
    except Exception:  # noqa: BLE001 - fake-bpy / partial envs lack bmesh
        return None
    mesh = obj.data
    if not getattr(mesh, "uv_layers", None) or len(mesh.uv_layers) == 0:
        return 0
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            return 0
        faces = list(bm.faces)
        if not faces:
            return 0
        parent = {f.index: f.index for f in faces}

        def find(a: int) -> int:
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a: int, b: int) -> None:
            parent[find(a)] = find(b)

        for edge in bm.edges:
            link = edge.link_loops
            if len(link) != 2:
                continue
            l1, l2 = link[0], link[1]
            # The two loops on each side that correspond to this edge's two verts.
            a1, b1 = l1[uv_layer].uv, l1.link_loop_next[uv_layer].uv
            a2, b2 = l2.link_loop_next[uv_layer].uv, l2[uv_layer].uv
            if _uv_eq(a1, a2) and _uv_eq(b1, b2):
                union(l1.face.index, l2.face.index)

        return len({find(f.index) for f in faces})
    finally:
        bm.free()


def _uv_eq(a: Any, b: Any, tol: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def report(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    mesh = obj.data
    uv_layers = list(getattr(mesh, "uv_layers", []) or [])
    layer_names = [getattr(layer, "name", "") for layer in uv_layers]
    active = getattr(getattr(mesh, "uv_layers", None), "active", None)
    return {
        "object": obj.name,
        "has_uvs": len(uv_layers) > 0,
        "uv_layers": layer_names,
        "uv_layer_count": len(uv_layers),
        "active_uv_layer": getattr(active, "name", None) if active is not None else None,
        "island_count": _island_count(obj),
    }


COMMANDS = [
    Command("uv.smart_unwrap", smart_unwrap, mutates=True, feedback="viewport"),
    Command("uv.unwrap", unwrap, mutates=True, feedback="viewport"),
    Command("uv.cube_project", cube_project, mutates=True, feedback="viewport"),
    Command("uv.sphere_project", sphere_project, mutates=True, feedback="viewport"),
    Command("uv.pack_islands", pack_islands, mutates=True, feedback="viewport"),
    Command("uv.average_islands_scale", average_islands_scale, mutates=True, feedback="viewport"),
    Command("uv.report", report, mutates=False),
]
