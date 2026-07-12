"""Engine-readiness metrics for Layer 2 optimize gates."""

from __future__ import annotations

import re
from typing import Any


def _scene_objects(ctx: Any) -> list[Any]:
    scene = getattr(getattr(ctx.bpy, "context", None), "scene", None)
    return list(getattr(scene, "objects", []) or [])


def _material_count(obj: Any) -> int:
    slots = list(getattr(obj, "material_slots", []) or [])
    if slots:
        return sum(1 for slot in slots if getattr(slot, "material", None) is not None)
    return len(list(getattr(getattr(obj, "data", None), "materials", []) or []))


def _material_iter(obj: Any) -> list[Any]:
    slots = list(getattr(obj, "material_slots", []) or [])
    if slots:
        return [slot.material for slot in slots if getattr(slot, "material", None) is not None]
    return [mat for mat in list(getattr(getattr(obj, "data", None), "materials", []) or []) if mat is not None]


def _image_key(image: Any) -> str:
    return str(getattr(image, "filepath", "") or getattr(image, "name", "") or id(image))


def _material_image_keys(material: Any) -> set[str]:
    keys: set[str] = set()
    nodes = list(getattr(getattr(material, "node_tree", None), "nodes", []) or [])
    for node in nodes:
        image = getattr(node, "image", None)
        if image is not None:
            keys.add(_image_key(image))
    slots = list(getattr(material, "texture_slots", []) or [])
    for slot in slots:
        texture = getattr(slot, "texture", None)
        image = getattr(texture, "image", None)
        if image is not None:
            keys.add(_image_key(image))
    return keys


def _texture_count(obj: Any) -> int:
    keys: set[str] = set()
    for material in _material_iter(obj):
        keys.update(_material_image_keys(material))
    return len(keys)


def _matches_lod(name: str, base: str) -> bool:
    if name == base:
        return False
    suffix = name[len(base):] if name.lower().startswith(base.lower()) else ""
    return bool(re.search(r"^[._-]?lod[._-]?\d+$", suffix, re.IGNORECASE))


def _matches_collision_proxy(name: str, base: str) -> bool:
    if name == base:
        return False
    lower = name.lower()
    base_lower = base.lower()
    return (
        lower in {f"{base_lower}_col", f"{base_lower}_collision", f"{base_lower}_collider"}
        or lower.startswith(f"ucx_{base_lower}")
        or lower.startswith(f"{base_lower}_ucx")
        or lower.startswith(f"{base_lower}_col_")
        or lower.startswith(f"{base_lower}_collision_")
    )


def _round_float(value: float) -> float:
    return round(float(value), 6)


def _triangle_count(obj: Any) -> int:
    polygons = list(getattr(getattr(obj, "data", None), "polygons", []) or [])
    total = 0
    for poly in polygons:
        total += max(len(getattr(poly, "vertices", []) or []) - 2, 0)
    return total


def _decimate_ratio(obj: Any) -> float | None:
    ratio = 1.0
    found = False
    for modifier in list(getattr(obj, "modifiers", []) or []):
        if str(getattr(modifier, "type", "")).upper() != "DECIMATE":
            continue
        try:
            ratio *= float(getattr(modifier, "ratio"))
            found = True
        except (TypeError, ValueError):
            continue
    if not found:
        return None
    return max(0.0, min(1.0, ratio))


def _lod_level(name: str, base: str) -> int | None:
    suffix = name[len(base):] if name.lower().startswith(base.lower()) else ""
    match = re.search(r"^[._-]?lod[._-]?(\d+)$", suffix, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _vec3(value: Any, default: list[float]) -> list[float]:
    try:
        items = [float(item) for item in value]
    except TypeError:
        return list(default)
    return items[:3] if len(items) >= 3 else list(default)


def _world_point(matrix: Any, point: list[float]) -> list[float]:
    if matrix is None:
        return point
    try:
        from mathutils import Vector  # noqa: PLC0415 - Blender-only import

        return _vec3(matrix @ Vector(point), point)
    except Exception:  # noqa: BLE001
        try:
            return _vec3(matrix @ point, point)
        except Exception:  # noqa: BLE001
            return point


def _bounds(obj: Any) -> dict[str, list[float]]:
    corners = [_vec3(corner, [0.0, 0.0, 0.0]) for corner in list(getattr(obj, "bound_box", []) or [])]
    if corners:
        matrix = getattr(obj, "matrix_world", None)
        world = [_world_point(matrix, corner) for corner in corners]
        mins = [min(point[i] for point in world) for i in range(3)]
        maxs = [max(point[i] for point in world) for i in range(3)]
    else:
        dims = _vec3(getattr(obj, "dimensions", None), [0.0, 0.0, 0.0])
        center = _vec3(getattr(obj, "location", None), [0.0, 0.0, 0.0])
        mins = [center[i] - (dims[i] / 2.0) for i in range(3)]
        maxs = [center[i] + (dims[i] / 2.0) for i in range(3)]
    dims = [maxs[i] - mins[i] for i in range(3)]
    return {
        "min": [_round_float(value) for value in mins],
        "max": [_round_float(value) for value in maxs],
        "dimensions": [_round_float(value) for value in dims],
    }


def _bounds_union(bounds: list[dict[str, list[float]]]) -> dict[str, list[float]] | None:
    if not bounds:
        return None
    mins = [min(item["min"][i] for item in bounds) for i in range(3)]
    maxs = [max(item["max"][i] for item in bounds) for i in range(3)]
    dims = [maxs[i] - mins[i] for i in range(3)]
    return {
        "min": [_round_float(value) for value in mins],
        "max": [_round_float(value) for value in maxs],
        "dimensions": [_round_float(value) for value in dims],
    }


def _bounds_delta(source: dict[str, list[float]], candidate: dict[str, list[float]]) -> float:
    deltas = []
    for index, source_dim in enumerate(source["dimensions"]):
        candidate_dim = candidate["dimensions"][index]
        if source_dim == 0:
            deltas.append(abs(candidate_dim - source_dim))
        else:
            deltas.append(abs(candidate_dim - source_dim) / source_dim)
    return _round_float(max(deltas) if deltas else 0.0)


def _bounds_cover(source: dict[str, list[float]], candidate: dict[str, list[float]] | None) -> bool:
    if candidate is None:
        return False
    eps = 1e-5
    return all(
        candidate["min"][i] <= source["min"][i] + eps and candidate["max"][i] >= source["max"][i] - eps
        for i in range(3)
    )


def _oversize_ratio(source: dict[str, list[float]], candidate: dict[str, list[float]] | None) -> float | None:
    if candidate is None:
        return None
    ratios = []
    for index, source_dim in enumerate(source["dimensions"]):
        extra = max(candidate["dimensions"][index] - source_dim, 0.0)
        ratios.append(extra if source_dim == 0 else extra / source_dim)
    return _round_float(max(ratios) if ratios else 0.0)


def engine_quality(ctx: Any, obj: Any, counts: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic game-engine readiness metrics for an object.

    This is intentionally engine-agnostic. Engine-specific export convention checks belong
    to later profile validators; this block only covers universal budget and proxy signals.
    """
    triangle_budget = int(payload.get("triangle_budget", 5000))
    material_budget = int(payload.get("material_budget", 4))
    texture_budget = int(payload.get("texture_budget", 8))
    min_lods = int(payload.get("min_lods", 1))
    max_lod_triangle_ratio = float(payload.get("max_lod_triangle_ratio", 0.75))
    max_lod_bounds_delta = float(payload.get("max_lod_bounds_delta", 0.1))
    min_collision_hulls = int(payload.get("min_collision_hulls", 1))
    max_collision_oversize_ratio = float(payload.get("max_collision_oversize_ratio", 0.5))
    material_count = _material_count(obj)
    texture_count = _texture_count(obj)
    object_name = str(getattr(obj, "name", ""))
    lod_count = 0
    collision_proxy_count = 0
    triangles = int(counts.get("tris", 0))
    source_bounds = _bounds(obj)
    lods = []
    collision_hulls = []
    collision_bounds = []
    for candidate in _scene_objects(ctx):
        name = str(getattr(candidate, "name", ""))
        if _matches_lod(name, object_name):
            lod_count += 1
            level = _lod_level(name, object_name) or lod_count
            lod_triangles = _triangle_count(candidate)
            ratio = _decimate_ratio(candidate)
            if ratio is not None and triangles > 0:
                lod_triangles = min(lod_triangles or triangles, max(0, round(triangles * ratio)))
            candidate_bounds = _bounds(candidate)
            lods.append(
                {
                    "name": name,
                    "level": level,
                    "triangles": int(lod_triangles),
                    "triangle_ratio": _round_float((lod_triangles / triangles) if triangles else 0.0),
                    "bounds_delta": _bounds_delta(source_bounds, candidate_bounds),
                }
            )
        if _matches_collision_proxy(name, object_name):
            collision_proxy_count += 1
            candidate_bounds = _bounds(candidate)
            collision_bounds.append(candidate_bounds)
            collision_hulls.append({"name": name, "dimensions": candidate_bounds["dimensions"]})
    lods.sort(key=lambda item: (item["level"], item["name"]))
    collision_union = _bounds_union(collision_bounds)
    collision_optional = min_collision_hulls == 0 and collision_proxy_count == 0
    collision_covers_source = True if collision_optional else _bounds_cover(source_bounds, collision_union)
    collision_oversize_ratio = 0.0 if collision_optional else _oversize_ratio(source_bounds, collision_union)
    collision_tight = (
        True
        if collision_optional
        else collision_oversize_ratio is not None and collision_oversize_ratio <= max_collision_oversize_ratio
    )
    has_collision_hulls = collision_proxy_count >= min_collision_hulls
    lod_triangle_reduction_ok = (
        all(item["triangle_ratio"] <= max_lod_triangle_ratio for item in lods) if lods else min_lods == 0
    )
    lod_silhouette_preserved = (
        all(item["bounds_delta"] <= max_lod_bounds_delta for item in lods) if lods else min_lods == 0
    )
    return {
        "triangles": triangles,
        "triangle_budget": triangle_budget,
        "within_triangle_budget": triangles <= triangle_budget,
        "materials": material_count,
        "material_budget": material_budget,
        "within_material_budget": material_count <= material_budget,
        "textures": texture_count,
        "texture_budget": texture_budget,
        "within_texture_budget": texture_count <= texture_budget,
        "lod_count": lod_count,
        "min_lods": min_lods,
        "has_lods": lod_count >= min_lods,
        "collision_proxy_count": collision_proxy_count,
        "has_collision_proxy": collision_proxy_count > 0,
        "lods": lods,
        "max_lod_triangle_ratio": max_lod_triangle_ratio,
        "lod_triangle_reduction_ok": lod_triangle_reduction_ok,
        "max_lod_bounds_delta": max_lod_bounds_delta,
        "lod_max_bounds_delta": _round_float(max((item["bounds_delta"] for item in lods), default=0.0)),
        "lod_silhouette_preserved": lod_silhouette_preserved,
        "collision_hulls": collision_hulls,
        "min_collision_hulls": min_collision_hulls,
        "has_collision_hulls": has_collision_hulls,
        "collision_bounds": collision_union,
        "collision_covers_source": collision_covers_source,
        "collision_oversize_ratio": collision_oversize_ratio,
        "max_collision_oversize_ratio": max_collision_oversize_ratio,
        "collision_tight": collision_tight,
        "collision_bounds_valid": collision_optional
        or (has_collision_hulls and collision_covers_source and collision_tight),
    }
