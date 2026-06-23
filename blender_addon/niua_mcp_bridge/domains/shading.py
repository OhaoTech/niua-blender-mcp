"""Shading domain handlers: materials + basic Principled shading.

Handlers stay tiny: the kernel does validation and pushes one undo step per
successful mutation. These ops are object-mode / datablock-level (no edit-mode
context needed), so they touch ``bpy.data`` and the material ``node_tree`` directly
rather than going through ``ctx.ensure``.

``shading.add_image_texture`` covers the deferred-light node case: it wires a single
``ShaderNodeTexImage`` into a Principled BSDF input. For BASE_COLOR/ROUGHNESS it links
the image directly; for NORMAL it inserts a ``ShaderNodeNormalMap`` between the image
and the Principled Normal input (and sets the image to Non-Color, the correct
colorspace for data textures).
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

# Principled BSDF input names per texture target, plus the colorspace a data texture
# (roughness/normal) should use. Base color is color data; the others are non-color.
_TARGET_INPUT = {
    "BASE_COLOR": ("Base Color", "sRGB"),
    "ROUGHNESS": ("Roughness", "Non-Color"),
    "NORMAL": ("Normal", "Non-Color"),
}
_PBR_MAPS = ("BASE_COLOR", "NORMAL", "ROUGHNESS", "AO", "CAVITY")
_PBR_COLORSPACE = {
    "BASE_COLOR": "sRGB",
    "NORMAL": "Non-Color",
    "ROUGHNESS": "Non-Color",
    "AO": "Non-Color",
    "CAVITY": "Non-Color",
}


def _get_material(ctx: Ctx, name: str) -> Any:
    mat = ctx.bpy.data.materials.get(name)
    if mat is None:
        raise BridgeError(NOT_FOUND, f"material not found: {name}")
    return mat


def _ensure_nodes(mat: Any) -> Any:
    """Guarantee the material uses nodes; return its node_tree."""
    if not getattr(mat, "use_nodes", False):
        mat.use_nodes = True
    return mat.node_tree


def _link_sockets(node_tree: Any, output_socket: Any, input_socket: Any) -> Any:
    return node_tree.links.new(input_socket, output_socket)


def _principled(node_tree: Any) -> Any:
    """Find (or create) the Principled BSDF node in a material node tree."""
    for node in node_tree.nodes:
        if getattr(node, "type", None) == "BSDF_PRINCIPLED":
            return node
    # No principled node (e.g. a stripped tree): add one. Output wiring is best-effort.
    node = node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    output = next(
        (n for n in node_tree.nodes if getattr(n, "type", None) == "OUTPUT_MATERIAL"),
        None,
    )
    if output is not None:
        _link_sockets(node_tree, node.outputs["BSDF"], output.inputs["Surface"])
    return node


def _resolve_material(ctx: Ctx, payload: dict) -> Any:
    """Resolve a material from 'material' name, else the active material of 'object'."""
    name = payload.get("material")
    if isinstance(name, str) and name:
        return _get_material(ctx, name)
    obj_name = payload.get("object")
    if isinstance(obj_name, str) and obj_name:
        obj = ctx.get_object(obj_name)
        mat = getattr(obj, "active_material", None)
        if mat is None:
            raise BridgeError(PRECONDITION, f"object has no active material: {obj_name}")
        return mat
    raise BridgeError(INVALID_PARAMS, "pass 'material' or 'object'")


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return value
    try:
        return [float(item) for item in value]
    except Exception:  # noqa: BLE001 - not a simple serializable value
        return None


def _socket_items(sockets: Any) -> list[Any]:
    values = getattr(sockets, "values", None)
    if callable(values):
        return list(values())
    return list(sockets or [])


def _socket_report(socket: Any) -> dict:
    return {
        "name": getattr(socket, "name", ""),
        "identifier": getattr(socket, "identifier", ""),
        "type": getattr(socket, "type", ""),
        "enabled": bool(getattr(socket, "enabled", True)),
        "is_linked": bool(getattr(socket, "is_linked", False)),
        "default_value": _json_value(getattr(socket, "default_value", None)),
    }


def _node_location(node: Any) -> list[float]:
    try:
        return [float(node.location[0]), float(node.location[1])]
    except Exception:  # noqa: BLE001
        return []


def _node_report(node: Any) -> dict:
    return {
        "name": getattr(node, "name", ""),
        "label": getattr(node, "label", ""),
        "type": getattr(node, "type", ""),
        "bl_idname": getattr(node, "bl_idname", ""),
        "location": _node_location(node),
        "inputs": [_socket_report(socket) for socket in _socket_items(getattr(node, "inputs", []))],
        "outputs": [_socket_report(socket) for socket in _socket_items(getattr(node, "outputs", []))],
    }


def _link_report(link: Any) -> dict:
    return {
        "from_node": getattr(getattr(link, "from_node", None), "name", ""),
        "from_socket": getattr(getattr(link, "from_socket", None), "name", ""),
        "to_node": getattr(getattr(link, "to_node", None), "name", ""),
        "to_socket": getattr(getattr(link, "to_socket", None), "name", ""),
    }


def _resolve_node(node_tree: Any, name: str) -> Any:
    nodes = getattr(node_tree, "nodes", None)
    getter = getattr(nodes, "get", None)
    node = getter(name) if callable(getter) else None
    if node is None:
        node = next((candidate for candidate in list(nodes or []) if getattr(candidate, "name", None) == name), None)
    if node is None:
        raise BridgeError(INVALID_PARAMS, f"node not found: {name}")
    return node


def _resolve_socket(sockets: Any, ref: str, *, node_name: str, direction: str) -> Any:
    items = _socket_items(sockets)
    if ref.isdigit():
        index = int(ref)
        if 0 <= index < len(items):
            return items[index]
        raise BridgeError(INVALID_PARAMS, f"{direction} socket index out of range: {node_name}[{index}]")
    getter = getattr(sockets, "get", None)
    socket = getter(ref) if callable(getter) else None
    if socket is None:
        socket = next(
            (
                candidate
                for candidate in items
                if getattr(candidate, "name", None) == ref or getattr(candidate, "identifier", None) == ref
            ),
            None,
        )
    if socket is None:
        raise BridgeError(INVALID_PARAMS, f"{direction} socket not found: {node_name}.{ref}")
    return socket


def _parse_json_value(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BridgeError(INVALID_PARAMS, f"value must be valid JSON: {exc}") from exc


def _parse_maps(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return list(_PBR_MAPS)
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "maps must be a comma-separated string")
    maps = [part.strip().upper() for part in raw.split(",") if part.strip()]
    if not maps:
        raise BridgeError(INVALID_PARAMS, "maps must contain at least one map")
    bad = [map_name for map_name in maps if map_name not in _PBR_MAPS]
    if bad:
        raise BridgeError(INVALID_PARAMS, f"unsupported PBR map: {bad[0]}")
    return maps


def _coerce_socket_default(current: Any, value: Any) -> Any:
    if current is None:
        return value
    if isinstance(current, bool):
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if isinstance(current, float):
        return float(value)
    if isinstance(current, str):
        return str(value)
    try:
        return tuple(float(item) for item in value)
    except Exception:  # noqa: BLE001 - let Blender validate unusual socket types
        return value


def _slot_report(obj: Any) -> list[dict]:
    data = getattr(obj, "data", None)
    slots = list(getattr(data, "materials", []) or [])
    return [{"index": index, "material": getattr(mat, "name", None)} for index, mat in enumerate(slots)]


def _material_report(mat: Any, obj: Any | None = None) -> dict:
    node_tree = getattr(mat, "node_tree", None)
    out = {
        "material": getattr(mat, "name", ""),
        "use_nodes": bool(getattr(mat, "use_nodes", False)),
        "diffuse_color": _json_value(getattr(mat, "diffuse_color", None)),
        "blend_method": getattr(mat, "blend_method", None),
        "use_screen_refraction": bool(getattr(mat, "use_screen_refraction", False)),
        "show_transparent_back": bool(getattr(mat, "show_transparent_back", True)),
        "nodes": [],
        "links": [],
    }
    if obj is not None:
        out["object"] = getattr(obj, "name", "")
        out["active_material_index"] = int(getattr(obj, "active_material_index", 0))
        out["slots"] = _slot_report(obj)
    if node_tree is not None:
        out["nodes"] = [_node_report(node) for node in list(getattr(node_tree, "nodes", []) or [])]
        out["links"] = [_link_report(link) for link in list(getattr(node_tree, "links", []) or [])]
    return out


# -- handlers --------------------------------------------------------------------


def create_material(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("name")
    name = name if isinstance(name, str) and name else "Material"
    mat = ctx.bpy.data.materials.new(name=name)
    mat.use_nodes = True
    return {"material": mat.name}


def set_principled(ctx: Ctx, payload: dict) -> dict:
    mat = _resolve_material(ctx, payload)
    node = _principled(_ensure_nodes(mat))
    inputs = node.inputs
    changed: dict[str, Any] = {}

    if "base_color" in payload and payload["base_color"] is not None:
        rgb = [float(v) for v in payload["base_color"]]
        alpha = float(payload["alpha"]) if payload.get("alpha") is not None else 1.0
        inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], alpha)
        changed["base_color"] = rgb
    if "alpha" in payload and payload["alpha"] is not None:
        alpha = float(payload["alpha"])
        inputs["Alpha"].default_value = alpha
        changed["alpha"] = alpha
    if "metallic" in payload and payload["metallic"] is not None:
        inputs["Metallic"].default_value = float(payload["metallic"])
        changed["metallic"] = float(payload["metallic"])
    if "roughness" in payload and payload["roughness"] is not None:
        inputs["Roughness"].default_value = float(payload["roughness"])
        changed["roughness"] = float(payload["roughness"])
    if "emission_strength" in payload and payload["emission_strength"] is not None:
        inputs["Emission Strength"].default_value = float(payload["emission_strength"])
        changed["emission_strength"] = float(payload["emission_strength"])

    return {"material": mat.name, "set": changed}


def _resolve_or_create_material_for_maps(ctx: Ctx, payload: dict) -> tuple[Any | None, Any, bool]:
    obj = None
    obj_name = payload.get("object")
    if isinstance(obj_name, str) and obj_name:
        obj = ctx.get_object(obj_name)

    mat_name = payload.get("material")
    mat = ctx.bpy.data.materials.get(mat_name) if isinstance(mat_name, str) and mat_name else None
    if mat is None and obj is not None and not (isinstance(mat_name, str) and mat_name):
        mat = getattr(obj, "active_material", None)

    created = False
    if mat is None:
        name = mat_name if isinstance(mat_name, str) and mat_name else f"{getattr(obj, 'name', 'Asset')}_PBR"
        mat = ctx.bpy.data.materials.new(name=name)
        mat.use_nodes = True
        created = True
    else:
        _ensure_nodes(mat)

    if obj is not None:
        data = getattr(obj, "data", None)
        materials = getattr(data, "materials", None)
        if materials is None:
            raise BridgeError(PRECONDITION, f"object cannot hold materials: {obj.name}")
        slots = list(materials)
        if mat in slots:
            index = slots.index(mat)
        else:
            materials.append(mat)
            index = len(slots)
        if hasattr(obj, "active_material_index"):
            obj.active_material_index = index
    return obj, mat, created


def _new_pbr_image(ctx: Ctx, name: str, size: int, map_name: str) -> Any:
    image = ctx.bpy.data.images.new(name=name, width=size, height=size, alpha=True)
    cs = getattr(image, "colorspace_settings", None)
    if cs is not None and hasattr(cs, "name"):
        cs.name = _PBR_COLORSPACE[map_name]
    return image


def _add_pbr_texture_node(node_tree: Any, principled: Any, image: Any, map_name: str) -> Any:
    tex = node_tree.nodes.new("ShaderNodeTexImage")
    tex.name = getattr(image, "name", map_name)
    tex.label = map_name
    tex.image = image
    if map_name == "BASE_COLOR":
        _link_sockets(node_tree, tex.outputs["Color"], principled.inputs["Base Color"])
    elif map_name == "ROUGHNESS":
        _link_sockets(node_tree, tex.outputs["Color"], principled.inputs["Roughness"])
    elif map_name == "NORMAL":
        normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
        normal_map.name = f"{getattr(image, 'name', 'Normal')}_NORMAL_MAP"
        normal_map.label = "NORMAL_MAP"
        _link_sockets(node_tree, tex.outputs["Color"], normal_map.inputs["Color"])
        _link_sockets(node_tree, normal_map.outputs["Normal"], principled.inputs["Normal"])
    return tex


def prepare_pbr_maps(ctx: Ctx, payload: dict) -> dict:
    obj, mat, created = _resolve_or_create_material_for_maps(ctx, payload)
    maps = _parse_maps(payload.get("maps"))
    size = int(payload.get("size", 1024))
    if size < 1:
        raise BridgeError(INVALID_PARAMS, "size must be >= 1")
    prefix = payload.get("prefix")
    if not isinstance(prefix, str) or not prefix:
        prefix = getattr(obj, "name", None) or getattr(mat, "name", "Asset")

    node_tree = _ensure_nodes(mat)
    principled = _principled(node_tree)
    created_maps = []
    for map_name in maps:
        image = _new_pbr_image(ctx, f"{prefix}_{map_name}", size, map_name)
        node = _add_pbr_texture_node(node_tree, principled, image, map_name)
        created_maps.append(
            {
                "map": map_name,
                "image": getattr(image, "name", ""),
                "node": getattr(node, "name", ""),
                "colorspace": getattr(getattr(image, "colorspace_settings", None), "name", ""),
                "size": [int(v) for v in list(getattr(image, "size", []) or [])[:2]],
            }
        )
    return {
        "object": getattr(obj, "name", None) if obj is not None else None,
        "material": getattr(mat, "name", ""),
        "created_material": created,
        "maps": maps,
        "created": created_maps,
    }


def assign_material(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(str(payload.get("object", "")))
    mat_name = str(payload.get("material", ""))
    mat = ctx.bpy.data.materials.get(mat_name)
    created = False
    if mat is None:
        mat = ctx.bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        created = True

    data = getattr(obj, "data", None)
    materials = getattr(data, "materials", None)
    if materials is None:
        raise BridgeError(PRECONDITION, f"object cannot hold materials: {obj.name}")

    slots = list(materials)
    if mat in slots:
        index = slots.index(mat)
    else:
        materials.append(mat)
        index = len(slots)
    # Make the assigned material the object's active slot.
    if hasattr(obj, "active_material_index"):
        obj.active_material_index = index

    return {"object": obj.name, "material": mat.name, "slot": index, "created": created}


def add_image_texture(ctx: Ctx, payload: dict) -> dict:
    mat = _get_material(ctx, str(payload.get("material", "")))
    image_path = str(payload.get("image_path", ""))
    if not image_path:
        raise BridgeError(INVALID_PARAMS, "image_path is required")
    target = str(payload.get("target", "BASE_COLOR")).upper()
    if target not in _TARGET_INPUT:
        raise BridgeError(INVALID_PARAMS, f"unsupported target: {target}")
    input_name, colorspace = _TARGET_INPUT[target]

    node_tree = _ensure_nodes(mat)
    principled = _principled(node_tree)

    try:
        image = ctx.bpy.data.images.load(image_path)
    except Exception as exc:  # noqa: BLE001 - Blender raises RuntimeError for bad image paths/formats
        raise BridgeError(PRECONDITION, f"could not load image: {exc}", {"path": image_path}) from exc
    tex = node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    # Data textures (roughness/normal) must be Non-Color to render correctly.
    cs = getattr(image, "colorspace_settings", None)
    if cs is not None and hasattr(cs, "name"):
        cs.name = colorspace

    if target == "NORMAL":
        normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
        _link_sockets(node_tree, tex.outputs["Color"], normal_map.inputs["Color"])
        _link_sockets(node_tree, normal_map.outputs["Normal"], principled.inputs[input_name])
    else:
        _link_sockets(node_tree, tex.outputs["Color"], principled.inputs[input_name])

    return {
        "material": mat.name,
        "image": getattr(image, "name", os.path.basename(image_path)),
        "target": target,
    }


def report(ctx: Ctx, payload: dict) -> dict:
    obj = None
    obj_name = payload.get("object")
    if isinstance(obj_name, str) and obj_name:
        obj = ctx.get_object(obj_name)
        mat = getattr(obj, "active_material", None)
        if mat is None:
            raise BridgeError(PRECONDITION, f"object has no active material: {obj_name}")
    else:
        mat = _get_material(ctx, str(payload.get("material", "")))
    return _material_report(mat, obj)


def add_node(ctx: Ctx, payload: dict) -> dict:
    mat = _get_material(ctx, str(payload.get("material", "")))
    node_tree = _ensure_nodes(mat)
    node_type = str(payload.get("type", ""))
    try:
        node = node_tree.nodes.new(node_type)
    except Exception as exc:  # noqa: BLE001 - Blender raises RuntimeError for unknown node ids
        raise BridgeError(INVALID_PARAMS, f"could not add node type {node_type}: {exc}") from exc
    name = payload.get("name")
    if isinstance(name, str) and name:
        node.name = name
    return {"material": mat.name, "node": _node_report(node)}


def link_nodes(ctx: Ctx, payload: dict) -> dict:
    mat = _get_material(ctx, str(payload.get("material", "")))
    node_tree = _ensure_nodes(mat)
    from_node = _resolve_node(node_tree, str(payload.get("from_node", "")))
    to_node = _resolve_node(node_tree, str(payload.get("to_node", "")))
    from_socket = _resolve_socket(
        getattr(from_node, "outputs", []),
        str(payload.get("from_socket", "")),
        node_name=getattr(from_node, "name", ""),
        direction="output",
    )
    to_socket = _resolve_socket(
        getattr(to_node, "inputs", []),
        str(payload.get("to_socket", "")),
        node_name=getattr(to_node, "name", ""),
        direction="input",
    )
    try:
        created = _link_sockets(node_tree, from_socket, to_socket)
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(INVALID_PARAMS, f"could not link sockets: {exc}") from exc
    return {
        "material": mat.name,
        "link": _link_report(created),
        "links": [_link_report(link) for link in list(getattr(node_tree, "links", []) or [])],
    }


def set_node_input(ctx: Ctx, payload: dict) -> dict:
    mat = _get_material(ctx, str(payload.get("material", "")))
    node_tree = _ensure_nodes(mat)
    node = _resolve_node(node_tree, str(payload.get("node", "")))
    socket = _resolve_socket(
        getattr(node, "inputs", []),
        str(payload.get("input", "")),
        node_name=getattr(node, "name", ""),
        direction="input",
    )
    value = _parse_json_value(payload.get("value"))
    try:
        socket.default_value = _coerce_socket_default(getattr(socket, "default_value", None), value)
    except Exception as exc:  # noqa: BLE001
        raise BridgeError(INVALID_PARAMS, f"could not set socket default: {exc}") from exc
    return {"material": mat.name, "node": getattr(node, "name", ""), "input": _socket_report(socket)}


def list_materials(ctx: Ctx, payload: dict) -> dict:
    obj_name = payload.get("object")
    if isinstance(obj_name, str) and obj_name:
        obj = ctx.get_object(obj_name)
        data = getattr(obj, "data", None)
        slots = list(getattr(data, "materials", []) or [])
        return {
            "object": obj.name,
            "materials": [getattr(m, "name", None) for m in slots if m is not None],
        }
    return {"materials": sorted(getattr(ctx.bpy.data, "materials", {}).keys())}


COMMANDS = [
    Command("shading.create_material", create_material, mutates=True),
    Command("shading.set_principled", set_principled, mutates=True, feedback="viewport"),
    Command("shading.prepare_pbr_maps", prepare_pbr_maps, mutates=True, feedback="viewport"),
    Command("shading.assign_material", assign_material, mutates=True, feedback="viewport"),
    Command("shading.add_image_texture", add_image_texture, mutates=True, feedback="viewport"),
    Command("shading.report", report, mutates=False),
    Command("shading.add_node", add_node, mutates=True, feedback="viewport"),
    Command("shading.link_nodes", link_nodes, mutates=True, feedback="viewport"),
    Command("shading.set_node_input", set_node_input, mutates=True, feedback="viewport"),
    Command("shading.list_materials", list_materials, mutates=False),
]
