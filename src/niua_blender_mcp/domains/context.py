"""Context / selection / mode tool specs."""

from __future__ import annotations

from ..kernel import Bool, Enum, Str, ToolSpec

MODES = [
    "OBJECT",
    "EDIT",
    "POSE",
    "SCULPT",
    "VERTEX_PAINT",
    "WEIGHT_PAINT",
    "TEXTURE_PAINT",
    "PARTICLE_EDIT",
    "EDIT_GPENCIL",
    "SCULPT_GREASE_PENCIL",
    "PAINT_GREASE_PENCIL",
    "WEIGHT_GREASE_PENCIL",
    "VERTEX_GREASE_PENCIL",
    "SCULPT_CURVES",
]

MESH_SELECT_MODES = ["VERT", "EDGE", "FACE", "VERT_EDGE", "VERT_FACE", "EDGE_FACE", "VERT_EDGE_FACE"]

SPECS = [
    ToolSpec(
        name="context.info",
        category="context",
        summary="Report active object, selected objects, mode, mesh select mode, and available areas",
        command="context.info",
    ),
    ToolSpec(
        name="context.areas",
        category="context",
        summary="List available editor areas for context overrides",
        command="context.areas",
    ),
    ToolSpec(
        name="context.set_active",
        category="context",
        summary="Set the active object and optionally select it",
        command="context.set_active",
        params={
            "object": Str(required=True, summary="Object to make active"),
            "select": Bool(default=True, summary="Also select the object"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="context.select_objects",
        category="context",
        summary="Update object selection by comma-separated object names",
        command="context.select_objects",
        params={
            "objects": Str(required=True, summary="Comma-separated object names"),
            "action": Enum(["REPLACE", "ADD", "REMOVE", "TOGGLE"], default="REPLACE"),
            "active": Str(default="", summary="Optional active object after selection"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="context.select_all",
        category="context",
        summary="Select, deselect, or invert selection for all scene objects",
        command="context.select_all",
        params={"action": Enum(["SELECT", "DESELECT", "INVERT"], default="DESELECT")},
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="context.mode_set",
        category="context",
        summary="Switch Blender interaction mode, optionally activating an object first",
        command="context.mode_set",
        params={
            "mode": Enum(MODES, required=True, summary="Interaction mode"),
            "object": Str(default="", summary="Optional object to make active first"),
            "select": Bool(default=True, summary="Select the object before switching mode"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="context.mesh_select_mode",
        category="context",
        summary="Set mesh edit selection mode",
        command="context.mesh_select_mode",
        params={"mode": Enum(MESH_SELECT_MODES, required=True, summary="Mesh select mode")},
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="context.poll_operator",
        category="context",
        summary="Check whether a Blender operator polls in the current or proposed context",
        command="context.poll_operator",
        params={
            "idname": Str(required=True, summary="Operator id, e.g. mesh.subdivide"),
            "object": Str(default="", summary="Optional active object for the poll"),
            "mode": Str(default="", summary="Optional mode for the poll"),
            "select": Str(default="", summary="Optional comma-separated selected objects"),
        },
    ),
]
