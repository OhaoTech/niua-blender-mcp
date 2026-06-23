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


def engine_quality(ctx: Any, obj: Any, counts: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic game-engine readiness metrics for an object.

    This is intentionally engine-agnostic. Engine-specific export convention checks belong
    to later profile validators; this block only covers universal budget and proxy signals.
    """
    triangle_budget = int(payload.get("triangle_budget", 5000))
    material_budget = int(payload.get("material_budget", 4))
    texture_budget = int(payload.get("texture_budget", 8))
    min_lods = int(payload.get("min_lods", 1))
    material_count = _material_count(obj)
    texture_count = _texture_count(obj)
    object_name = str(getattr(obj, "name", ""))
    lod_count = 0
    collision_proxy_count = 0
    for candidate in _scene_objects(ctx):
        name = str(getattr(candidate, "name", ""))
        if _matches_lod(name, object_name):
            lod_count += 1
        if _matches_collision_proxy(name, object_name):
            collision_proxy_count += 1
    triangles = int(counts.get("tris", 0))
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
    }
