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

import os
from typing import Any

from ..context import Ctx
from ..core.uv_metrics import uv_quality
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

UV_EXPORT_EXT_TO_FORMAT = {"png": "PNG", "svg": "SVG", "eps": "EPS"}
UV_EXPORT_FORMATS = {"PNG", "SVG", "EPS"}


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


def _uv_layers(obj: Any) -> Any:
    return getattr(getattr(obj, "data", None), "uv_layers", None)


def _layer_report(obj: Any) -> dict:
    layers = list(_uv_layers(obj) or [])
    active = getattr(_uv_layers(obj), "active", None)
    names = [getattr(layer, "name", "") for layer in layers]
    active_name = getattr(active, "name", None) if active is not None else None
    return {
        "object": obj.name,
        "layers": names,
        "count": len(layers),
        "active": active_name,
        "active_index": names.index(active_name) if active_name in names else None,
    }


def _get_uv_layer(obj: Any, name: str) -> Any:
    layers = _uv_layers(obj)
    getter = getattr(layers, "get", None)
    layer = getter(name) if callable(getter) else None
    if layer is None:
        layer = next((candidate for candidate in list(layers or []) if getattr(candidate, "name", None) == name), None)
    if layer is None:
        raise BridgeError(NOT_FOUND, f"UV layer not found: {name}", {"object": getattr(obj, "name", "?")})
    return layer


def layers(ctx: Ctx, payload: dict) -> dict:
    return _layer_report(_resolve_mesh(ctx, payload))


def layer_create(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    name = payload.get("name")
    name = name if isinstance(name, str) and name else "UVMap"
    _uv_layers(obj).new(name=name, do_init=bool(payload.get("do_init", True)))
    return _layer_report(obj)


def layer_set_active(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    _uv_layers(obj).active = _get_uv_layer(obj, str(payload.get("name", "")))
    return _layer_report(obj)


def layer_delete(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    layer = _get_uv_layer(obj, str(payload.get("name", "")))
    _uv_layers(obj).remove(layer)
    return _layer_report(obj)


def _edge_report(obj: Any) -> dict:
    edges = list(getattr(getattr(obj, "data", None), "edges", []) or [])
    return {
        "object": obj.name,
        "edge_count": len(edges),
        "seam_edges": [index for index, edge in enumerate(edges) if bool(getattr(edge, "use_seam", False))],
    }


def _parse_edge_indices(obj: Any, raw: Any) -> list[int]:
    edges = list(getattr(getattr(obj, "data", None), "edges", []) or [])
    if raw is None or raw == "":
        return []
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "edges must be a comma-separated string")
    out: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            index = int(item)
        except ValueError as exc:
            raise BridgeError(INVALID_PARAMS, f"invalid edge index: {item}") from exc
        if index < 0 or index >= len(edges):
            raise BridgeError(INVALID_PARAMS, f"edge index out of range: {index}", {"edge_count": len(edges)})
        out.append(index)
    return out


def seams(ctx: Ctx, payload: dict) -> dict:
    return _edge_report(_resolve_mesh(ctx, payload))


def set_seams(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    edges = list(getattr(obj.data, "edges", []) or [])
    action = str(payload.get("action", "SET")).upper()
    indices = _parse_edge_indices(obj, payload.get("edges", ""))
    if action == "CLEAR":
        for edge in edges:
            edge.use_seam = False
        return _edge_report(obj)
    if action == "SET":
        for edge in edges:
            edge.use_seam = False
        for index in indices:
            edges[index].use_seam = True
    elif action == "ADD":
        for index in indices:
            edges[index].use_seam = True
    elif action == "REMOVE":
        for index in indices:
            edges[index].use_seam = False
    else:
        raise BridgeError(INVALID_PARAMS, f"unsupported seam action: {action}")
    return _edge_report(obj)


def _infer_layout_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    fmt = UV_EXPORT_EXT_TO_FORMAT.get(ext)
    if fmt is None:
        raise BridgeError(
            INVALID_PARAMS,
            f"cannot infer UV layout format from extension: {ext or '(none)'}",
            {"path": path, "extension": ext, "supported": sorted(UV_EXPORT_EXT_TO_FORMAT)},
        )
    return fmt


def export_layout(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_mesh(ctx, payload)
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required")

    fmt = str(payload.get("format", "AUTO")).upper()
    if fmt in ("", "AUTO"):
        fmt = _infer_layout_format(path)
    if fmt not in UV_EXPORT_FORMATS:
        raise BridgeError(
            INVALID_PARAMS,
            f"unsupported UV layout format: {fmt}",
            {"supported": sorted(UV_EXPORT_FORMATS)},
        )

    size = int(payload.get("size", 1024))
    opacity = float(payload.get("opacity", 0.25))
    export_all = bool(payload.get("export_all", True))
    modified = bool(payload.get("modified", False))
    op = ctx.bpy.ops.uv.export_layout

    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ctx.bpy.ops.mesh.select_all)
        ctx.bpy.ops.mesh.select_all(action="SELECT")
        ctx.check_poll(op)
        try:
            op(
                filepath=path,
                size=(size, size),
                opacity=opacity,
                export_all=export_all,
                modified=modified,
                mode=fmt,
            )
        except Exception as exc:  # noqa: BLE001 - Blender operators raise RuntimeError/SystemError
            raise BridgeError(
                PRECONDITION,
                f"could not export UV layout: {exc}",
                {"path": path, "format": fmt},
            ) from exc

    return {
        "object": obj.name,
        "path": path,
        "size": size,
        "opacity": opacity,
        "export_all": export_all,
        "modified": modified,
        "format": fmt,
        "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
    }


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
    island_count = _island_count(obj)
    out = {
        "object": obj.name,
        "has_uvs": len(uv_layers) > 0,
        "uv_layers": layer_names,
        "uv_layer_count": len(uv_layers),
        "active_uv_layer": getattr(active, "name", None) if active is not None else None,
        "island_count": island_count,
    }
    out.update(uv_quality(obj, island_count=island_count))
    # Preserve explicit layer names from this handler; uv_quality only reports counts.
    out["uv_layers"] = layer_names
    return out


COMMANDS = [
    Command("uv.layers", layers, mutates=False),
    Command("uv.layer_create", layer_create, mutates=True, feedback="viewport"),
    Command("uv.layer_set_active", layer_set_active, mutates=True, feedback="viewport"),
    Command("uv.layer_delete", layer_delete, mutates=True, feedback="viewport"),
    Command("uv.seams", seams, mutates=False),
    Command("uv.set_seams", set_seams, mutates=True, feedback="viewport"),
    Command("uv.export_layout", export_layout, mutates=True, feedback="viewport"),
    Command("uv.smart_unwrap", smart_unwrap, mutates=True, feedback="viewport"),
    Command("uv.unwrap", unwrap, mutates=True, feedback="viewport"),
    Command("uv.cube_project", cube_project, mutates=True, feedback="viewport"),
    Command("uv.sphere_project", sphere_project, mutates=True, feedback="viewport"),
    Command("uv.pack_islands", pack_islands, mutates=True, feedback="viewport"),
    Command("uv.average_islands_scale", average_islands_scale, mutates=True, feedback="viewport"),
    Command("uv.report", report, mutates=False),
]
