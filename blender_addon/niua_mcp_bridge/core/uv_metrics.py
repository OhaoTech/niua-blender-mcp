"""UV quality metrics for Layer 2 gates."""

from __future__ import annotations

import math
from typing import Any

EPSILON = 1e-9


def polygon_area_2d(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    acc = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_on_segment(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> bool:
    if abs(_orientation(a, b, point)) > EPSILON:
        return False
    return (
        min(a[0], b[0]) - EPSILON <= point[0] <= max(a[0], b[0]) + EPSILON
        and min(a[1], b[1]) - EPSILON <= point[1] <= max(a[1], b[1]) + EPSILON
    )


def _segments_properly_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    first = _orientation(a1, a2, b1)
    second = _orientation(a1, a2, b2)
    third = _orientation(b1, b2, a1)
    fourth = _orientation(b1, b2, a2)
    return first * second < -EPSILON and third * fourth < -EPSILON


def _point_in_polygon_strict(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        if _point_on_segment(point, start, end):
            return False

    inside = False
    x, y = point
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            x_at_y = x1 + ((y - y1) * (x2 - x1) / (y2 - y1))
            if x_at_y > x:
                inside = not inside
    return inside


def polygons_overlap_2d(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    """Return true only when two polygons share positive area."""
    if len(a) < 3 or len(b) < 3:
        return False

    a_min_x = min(point[0] for point in a)
    a_max_x = max(point[0] for point in a)
    a_min_y = min(point[1] for point in a)
    a_max_y = max(point[1] for point in a)
    b_min_x = min(point[0] for point in b)
    b_max_x = max(point[0] for point in b)
    b_min_y = min(point[1] for point in b)
    b_max_y = max(point[1] for point in b)
    if a_max_x <= b_min_x + EPSILON or b_max_x <= a_min_x + EPSILON:
        return False
    if a_max_y <= b_min_y + EPSILON or b_max_y <= a_min_y + EPSILON:
        return False

    for a_index, a_start in enumerate(a):
        a_end = a[(a_index + 1) % len(a)]
        for b_index, b_start in enumerate(b):
            b_end = b[(b_index + 1) % len(b)]
            if _segments_properly_intersect(a_start, a_end, b_start, b_end):
                return True

    return any(_point_in_polygon_strict(point, b) for point in a) or any(
        _point_in_polygon_strict(point, a) for point in b
    )


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
        uv_polygons: list[list[tuple[float, float]]] = []
        for face in bm.faces:
            face_uvs = [(float(loop[uv_layer].uv[0]), float(loop[uv_layer].uv[1])) for loop in face.loops]
            uv_points.extend(face_uvs)
            if len(face_uvs) >= 3:
                uv_polygons.append(face_uvs)
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
        out["overlap_detected"] = any(
            polygons_overlap_2d(first, second)
            for first_index, first in enumerate(uv_polygons)
            for second in uv_polygons[first_index + 1 :]
        )
        return out
    finally:
        bm.free()
