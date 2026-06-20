"""Shading domain manifest: materials and basic principled shading.

Covers the hot path of material work: create a material, set its Principled BSDF
parameters (base color, metallic, roughness, emission), assign a material to an
object, and wire a single image-texture node to a Principled target (base color /
roughness / normal). ``shading.list_materials`` is read-only inventory.

Full arbitrary node-graph editing is deferred (DESIGN §12); this pack covers the
Principled BSDF plus one texture node wired to a target, which is object-mode safe.
"""

from __future__ import annotations

from ..kernel import Enum, Float, Str, ToolSpec, Vec3

TEXTURE_TARGETS = ["BASE_COLOR", "ROUGHNESS", "NORMAL"]

SPECS = [
    ToolSpec(
        name="shading.create_material",
        category="shading",
        summary="Create a new node-based material",
        command="shading.create_material",
        params={
            "name": Str(summary="Optional material name"),
        },
        mutates=True,
    ),
    ToolSpec(
        name="shading.set_principled",
        category="shading",
        summary="Set Principled BSDF parameters on a material",
        command="shading.set_principled",
        params={
            "material": Str(summary="Material name (else resolved from 'object')"),
            "object": Str(summary="Object whose active material to edit (if no 'material')"),
            "base_color": Vec3(summary="Base color RGB [r, g, b], each 0..1"),
            "alpha": Float(minimum=0.0, maximum=1.0, summary="Alpha (opacity) 0..1"),
            "metallic": Float(minimum=0.0, maximum=1.0, summary="Metallic 0..1"),
            "roughness": Float(minimum=0.0, maximum=1.0, summary="Roughness 0..1"),
            "emission_strength": Float(minimum=0.0, summary="Emission strength"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shading.assign_material",
        category="shading",
        summary="Assign a material to an object (creates it if missing)",
        command="shading.assign_material",
        params={
            "object": Str(required=True, summary="Object to receive the material"),
            "material": Str(required=True, summary="Material name (created if it does not exist)"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shading.add_image_texture",
        category="shading",
        summary="Wire an image-texture node to a Principled BSDF target",
        command="shading.add_image_texture",
        params={
            "material": Str(required=True, summary="Material to edit"),
            "image_path": Str(required=True, summary="Filesystem path to the image to load"),
            "target": Enum(
                TEXTURE_TARGETS,
                default="BASE_COLOR",
                summary="Principled input to drive: BASE_COLOR, ROUGHNESS or NORMAL",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shading.report",
        category="shading",
        summary="Report a material, object material slots, and shader node tree",
        command="shading.report",
        params={
            "material": Str(default="", summary="Material name"),
            "object": Str(default="", summary="Object whose active material and slots should be reported"),
        },
    ),
    ToolSpec(
        name="shading.add_node",
        category="shading",
        summary="Add a shader node to a material node tree",
        command="shading.add_node",
        params={
            "material": Str(required=True, summary="Material to edit"),
            "type": Str(required=True, summary="Shader node bl_idname, e.g. ShaderNodeTexNoise"),
            "name": Str(default="", summary="Optional node name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shading.link_nodes",
        category="shading",
        summary="Link two shader node sockets",
        command="shading.link_nodes",
        params={
            "material": Str(required=True, summary="Material to edit"),
            "from_node": Str(required=True, summary="Source node name"),
            "from_socket": Str(required=True, summary="Source output socket name or index"),
            "to_node": Str(required=True, summary="Destination node name"),
            "to_socket": Str(required=True, summary="Destination input socket name or index"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shading.set_node_input",
        category="shading",
        summary="Set a shader node input default value from JSON",
        command="shading.set_node_input",
        params={
            "material": Str(required=True, summary="Material to edit"),
            "node": Str(required=True, summary="Node name"),
            "input": Str(required=True, summary="Input socket name or index"),
            "value": Str(required=True, summary="JSON scalar or array value"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="shading.list_materials",
        category="shading",
        summary="List materials in the file (read-only)",
        command="shading.list_materials",
        params={
            "object": Str(summary="Limit to one object's material slots"),
        },
    ),
]
