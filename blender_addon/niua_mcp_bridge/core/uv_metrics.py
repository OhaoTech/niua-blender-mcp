"""UV quality metrics for Layer 2 gates."""

from __future__ import annotations

import math
from typing import Any


def polygon_area_2d(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    acc = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


def uv_bounds_from_points(points: list[tuple[float, float]]) -> dict:
    if not points:
        return {"min_u": None, "min_v": None, "max_u": None, "max_v": None, "out_of_bounds_loops": 0}
    us = [p[0] for p in points]
    vs = [p[1] for p in points]
    out_of_bounds = sum(1 for u, v in points if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0)
    return {
        "min_u": min(us),
        "min_v": min(vs),
        "max_u": max(us),
        "max_v": max(vs),
        "out_of_bounds_loops": out_of_bounds,
    }


def uv_quality(obj: Any, *, texture_size: int = 1024, island_count: int | None = None) -> dict:
    layers = list(getattr(getattr(obj, "data", None), "uv_layers", []) or [])
    active = getattr(getattr(getattr(obj, "data", None), "uv_layers", None), "active", None)
    out = {
        "has_uvs": len(layers) > 0,
        "uv_layer_count": len(layers),
        "active_uv_layer": getattr(active, "name", None) if active is not None else None,
        "island_count": island_count,
        "uv_bounds": {"min_u": None, "min_v": None, "max_u": None, "max_v": None},
        "out_of_bounds_loops": None,
        "uv_area": None,
        "mesh_area": None,
        "texel_density_px_per_unit": None,
        "overlap_detected": None,
        "stretch_ratio": None,
    }
    try:
        import bmesh  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - fake-bpy and server envs do not have bmesh
        return out

    if not layers:
        out["out_of_bounds_loops"] = 0
        return out

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            out["out_of_bounds_loops"] = 0
            return out

        uv_points: list[tuple[float, float]] = []
        uv_area = 0.0
        mesh_area = 0.0
        stretch_units: list[float] = []
        for face in bm.faces:
            face_uvs = [(float(loop[uv_layer].uv[0]), float(loop[uv_layer].uv[1])) for loop in face.loops]
            uv_points.extend(face_uvs)
            face_uv_area = polygon_area_2d(face_uvs)
            face_mesh_area = float(face.calc_area())
            uv_area += face_uv_area
            mesh_area += face_mesh_area
            if face_uv_area > 0.0 and face_mesh_area > 0.0:
                stretch_units.append(math.sqrt(face_mesh_area) / math.sqrt(face_uv_area))

        bounds = uv_bounds_from_points(uv_points)
        out["uv_bounds"] = {key: bounds[key] for key in ("min_u", "min_v", "max_u", "max_v")}
        out["out_of_bounds_loops"] = bounds["out_of_bounds_loops"]
        out["uv_area"] = uv_area
        out["mesh_area"] = mesh_area
        if uv_area > 0.0 and mesh_area > 0.0:
            out["texel_density_px_per_unit"] = texture_size * math.sqrt(uv_area / mesh_area)
        if stretch_units:
            smallest = min(stretch_units)
            out["stretch_ratio"] = (max(stretch_units) / smallest) if smallest > 0.0 else None
        return out
    finally:
        bm.free()
