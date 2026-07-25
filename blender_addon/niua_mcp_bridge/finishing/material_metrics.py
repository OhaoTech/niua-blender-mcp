"""Material production metrics for Layer 2 bake/material gates."""

from __future__ import annotations

from typing import Any

PBR_MAPS = ("BASE_COLOR", "NORMAL", "ROUGHNESS", "AO", "CAVITY")
# Bake gate matches object.bake_transfer / bake_and_finish (NORMAL+AO). CAVITY is
# optional PBR garnish from prepare_pbr_maps, not required to pass the bake stage.
BAKE_MAPS = ("NORMAL", "AO")
DATA_MAPS = ("NORMAL", "ROUGHNESS", "AO", "CAVITY")

_ALIASES = {
    "BASE_COLOR": ("BASE_COLOR", "BASECOLOR", "ALBEDO", "DIFFUSE", "COLOR"),
    "NORMAL": ("NORMAL", "NRM", "NORM"),
    "ROUGHNESS": ("ROUGHNESS", "ROUGH"),
    "AO": ("AO", "AMBIENT_OCCLUSION", "AMBIENTOCCLUSION"),
    "CAVITY": ("CAVITY", "CURVATURE"),
}


def _materials(obj: Any) -> list[Any]:
    slots = list(getattr(obj, "material_slots", []) or [])
    if slots:
        return [slot.material for slot in slots if getattr(slot, "material", None) is not None]
    return [mat for mat in list(getattr(getattr(obj, "data", None), "materials", []) or []) if mat is not None]


def _image_key(image: Any) -> str:
    return str(getattr(image, "filepath", "") or getattr(image, "name", "") or id(image))


def _image_size(image: Any) -> list[int]:
    try:
        return [int(v) for v in list(getattr(image, "size", []) or [])[:2]]
    except Exception:  # noqa: BLE001 - malformed fake/partial image data
        return []


def _image_colorspace(image: Any) -> str:
    return str(getattr(getattr(image, "colorspace_settings", None), "name", ""))


def _node_image(node: Any) -> Any | None:
    if getattr(node, "type", None) != "TEX_IMAGE":
        return None
    return getattr(node, "image", None)


def _detect_map(node: Any, image: Any) -> str | None:
    text = " ".join(
        str(part)
        for part in (
            getattr(node, "label", ""),
            getattr(node, "name", ""),
            getattr(image, "name", ""),
            getattr(image, "filepath", ""),
        )
        if part
    ).upper()
    compact = text.replace(" ", "_").replace("-", "_").replace(".", "_")
    for map_name, aliases in _ALIASES.items():
        if any(alias in compact for alias in aliases):
            return map_name
    return None


def _texture_nodes(material: Any) -> list[dict[str, Any]]:
    nodes = list(getattr(getattr(material, "node_tree", None), "nodes", []) or [])
    out: list[dict[str, Any]] = []
    for node in nodes:
        image = _node_image(node)
        if image is None:
            continue
        out.append(
            {
                "material": getattr(material, "name", ""),
                "node": getattr(node, "name", ""),
                "label": getattr(node, "label", ""),
                "map": _detect_map(node, image),
                "image": getattr(image, "name", ""),
                "filepath": getattr(image, "filepath", ""),
                "size": _image_size(image),
                "colorspace": _image_colorspace(image),
                "key": _image_key(image),
            }
        )
    return out


def material_quality(obj: Any, payload: dict[str, Any]) -> dict[str, Any]:
    max_texture_size = int(payload.get("max_texture_size", 2048))
    materials = _materials(obj)
    texture_nodes: list[dict[str, Any]] = []
    for material in materials:
        texture_nodes.extend(_texture_nodes(material))

    image_keys = {entry["key"] for entry in texture_nodes}
    present_maps = sorted({entry["map"] for entry in texture_nodes if entry["map"] in PBR_MAPS})
    missing_maps = [map_name for map_name in PBR_MAPS if map_name not in present_maps]

    def _map_entries(map_name: str) -> list[dict[str, Any]]:
        return [entry for entry in texture_nodes if entry["map"] == map_name]

    # Only judge colorspace on data maps that are actually present (bake may only
    # produce NORMAL+AO; missing ROUGHNESS/CAVITY must not fail the bake gate).
    present_data_maps = [map_name for map_name in DATA_MAPS if map_name in present_maps]
    data_maps_non_color = bool(present_data_maps) and all(
        all(entry["colorspace"] == "Non-Color" for entry in _map_entries(map_name))
        for map_name in present_data_maps
    )
    textures_within_size = bool(texture_nodes) and all(
        entry["size"] and max(entry["size"]) <= max_texture_size for entry in texture_nodes
    )
    square_textures = bool(texture_nodes) and all(
        len(entry["size"]) == 2 and entry["size"][0] == entry["size"][1] for entry in texture_nodes
    )
    pbr_maps_present = not missing_maps
    bake_maps_present = all(map_name in present_maps for map_name in BAKE_MAPS)
    atlas_ready = pbr_maps_present and data_maps_non_color and textures_within_size and square_textures
    return {
        "material_count": len(materials),
        "texture_count": len(image_keys),
        "texture_node_count": len(texture_nodes),
        "required_maps": list(PBR_MAPS),
        "present_maps": present_maps,
        "missing_maps": missing_maps,
        "bake_maps_present": bake_maps_present,
        "pbr_maps_present": pbr_maps_present,
        "data_maps_non_color": data_maps_non_color,
        "max_texture_size": max_texture_size,
        "textures_within_size": textures_within_size,
        "square_textures": square_textures,
        "atlas_ready": atlas_ready,
        "textures": [
            {key: value for key, value in entry.items() if key != "key"} for entry in texture_nodes
        ],
    }
