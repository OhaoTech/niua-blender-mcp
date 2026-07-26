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


#: A face may register in at most this many grid cells. Beyond it the face is "oversized"
#: and handled separately -- see _uv_overlap_detected.
_MAX_CELLS_PER_FACE = 64


def _uv_overlap_detected(uv_polygons: list[list[tuple[float, float]]]) -> bool:
    """Whether any two UV faces share positive area.

    Equivalent to the all-pairs ``polygons_overlap_2d`` scan, but a uniform spatial-grid
    broad-phase makes it ~O(n) for spread-out UVs: faces are bucketed by their bbox into ~n
    cells and only faces sharing a cell are tested. Two overlapping faces necessarily have
    overlapping bboxes and therefore share a cell, so no overlap is missed.

    A uniform grid is only near-linear when faces are of *similar* size, and that assumption
    is not free. A face whose bbox spans the whole UV range registers in ``cells x cells``
    buckets -- with n=489k faces that is ~488,000 insertions for ONE face, so a handful of
    them turns insertion alone into O(n^2). This is not hypothetical: ``mesh.tris_to_quads``
    merges triangle pairs that sat on different UV islands, and the resulting quad's UV bbox
    spans both. Measured on the real_prop fixture (978k tris), that took uv.report from 12.7s
    to over 142s and blew the finisher's 120s measurement budget, which left the asset
    unmeasured and invalidated a whole benchmark run.

    So per-face insertion is capped: a face spanning more than ``_MAX_CELLS_PER_FACE`` cells
    is pulled out as *oversized* and tested directly against every other face (with a bbox
    reject first). Correctness is unchanged -- an overlapping pair is still always compared,
    either through a shared cell or through the oversized pass. Oversized faces are tested
    FIRST because a face covering much of the UV space is very likely to hit something, and
    the first hit returns immediately.
    """
    n = len(uv_polygons)
    if n < 2:
        return False

    # Precompute each face's bbox once (the old inner loop recomputed 8 min/max per pair).
    boxes: list[tuple[float, float, float, float]] = []
    for poly in uv_polygons:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        boxes.append((min(xs), max(xs), min(ys), max(ys)))

    min_x = min(b[0] for b in boxes)
    max_x = max(b[1] for b in boxes)
    min_y = min(b[2] for b in boxes)
    max_y = max(b[3] for b in boxes)
    span_x = max(max_x - min_x, EPSILON)
    span_y = max(max_y - min_y, EPSILON)
    cells = max(1, int(math.sqrt(n)))  # ~n cells total -> ~1 face per cell for a spread-out UV
    inv_x = cells / span_x
    inv_y = cells / span_y

    def _bbox_disjoint(a: tuple[float, float, float, float],
                       b: tuple[float, float, float, float]) -> bool:
        return (a[1] <= b[0] + EPSILON or b[1] <= a[0] + EPSILON
                or a[3] <= b[2] + EPSILON or b[3] <= a[2] + EPSILON)

    grid: dict[tuple[int, int], list[int]] = {}
    oversized: list[int] = []
    for i, (bx0, bx1, by0, by1) in enumerate(boxes):
        cx0 = int((bx0 - min_x) * inv_x)
        cx1 = int((bx1 - min_x) * inv_x)
        cy0 = int((by0 - min_y) * inv_y)
        cy1 = int((by1 - min_y) * inv_y)
        # Cap the work one face can create. Without this a single UV-space-spanning face
        # inserts into cells*cells buckets and the broad-phase degenerates to O(n^2).
        if (cx1 - cx0 + 1) * (cy1 - cy0 + 1) > _MAX_CELLS_PER_FACE:
            oversized.append(i)
            continue
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                grid.setdefault((cx, cy), []).append(i)

    # Oversized faces first: they cover a lot of UV space, so a hit is likely and returns
    # immediately. Each is compared against every other face, bbox-rejected before the
    # O(edges) polygon test, which preserves the "no overlap is ever missed" guarantee.
    done_oversized: set[int] = set()
    for i in oversized:
        bi = boxes[i]
        for j in range(n):
            if j == i or j in done_oversized:   # that pair was already compared
                continue
            if _bbox_disjoint(bi, boxes[j]):
                continue
            if polygons_overlap_2d(uv_polygons[i], uv_polygons[j]):
                return True
        done_oversized.add(i)

    checked: set[tuple[int, int]] = set()
    for bucket in grid.values():
        m = len(bucket)
        for a in range(m):
            i = bucket[a]
            bi = boxes[i]
            for b in range(a + 1, m):
                j = bucket[b]
                key = (i, j) if i < j else (j, i)
                if key in checked:
                    continue
                checked.add(key)
                bj = boxes[j]
                # cheap bbox reject before the O(edges) polygon test
                if bi[1] <= bj[0] + EPSILON or bj[1] <= bi[0] + EPSILON:
                    continue
                if bi[3] <= bj[2] + EPSILON or bj[3] <= bi[2] + EPSILON:
                    continue
                if polygons_overlap_2d(uv_polygons[i], uv_polygons[j]):
                    return True
    return False


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
        out["overlap_detected"] = _uv_overlap_detected(uv_polygons)
        return out
    finally:
        bm.free()
