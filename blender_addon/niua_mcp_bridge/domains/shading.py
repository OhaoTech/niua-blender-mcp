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
        node_tree.links.new(node.outputs["BSDF"], output.inputs["Surface"])
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

    image = ctx.bpy.data.images.load(image_path)
    tex = node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    # Data textures (roughness/normal) must be Non-Color to render correctly.
    cs = getattr(image, "colorspace_settings", None)
    if cs is not None and hasattr(cs, "name"):
        cs.name = colorspace

    if target == "NORMAL":
        normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
        node_tree.links.new(tex.outputs["Color"], normal_map.inputs["Color"])
        node_tree.links.new(normal_map.outputs["Normal"], principled.inputs[input_name])
    else:
        node_tree.links.new(tex.outputs["Color"], principled.inputs[input_name])

    return {
        "material": mat.name,
        "image": getattr(image, "name", os.path.basename(image_path)),
        "target": target,
    }


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
    Command("shading.assign_material", assign_material, mutates=True, feedback="viewport"),
    Command("shading.add_image_texture", add_image_texture, mutates=True, feedback="viewport"),
    Command("shading.list_materials", list_materials, mutates=False),
]
