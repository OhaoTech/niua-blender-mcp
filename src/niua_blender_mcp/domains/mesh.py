"""Mesh domain manifest: the first real modeling capability.

Edit-mode operators (extrude/bevel/inset/subdivide/recalc_normals) act on the active
mesh object's selection; the kernel context resolver guarantees EDIT mode + a mesh
active object + a selection before they run. ``mesh.shade_smooth`` is an object-mode
shading toggle. ``mesh.report`` is read-only analytic feedback ("the eyes"): topology
counts, n-gons, non-manifold edges, bbox dimensions, UV/material counts.
"""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec, Vec3

SELECT_ALL_ACTIONS = ["TOGGLE", "SELECT", "DESELECT", "INVERT"]
MESH_ELEMENT_MODES = ["VERT", "EDGE", "FACE"]
MESH_SELECTION_ACTIONS = ["REPLACE", "ADD", "REMOVE", "TOGGLE"]
MESH_DELETE_TYPES = ["VERT", "EDGE", "FACE", "EDGE_FACE", "ONLY_FACE"]
MESH_DISSOLVE_TYPES = ["VERTS", "EDGES", "FACES", "LIMITED"]

SPECS = [
    ToolSpec(
        name="mesh.extrude",
        category="mesh",
        summary="Extrude the selected region and translate it",
        command="mesh.extrude",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "translate": Vec3(summary="Translation applied to the extruded region [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.bevel",
        category="mesh",
        summary="Bevel the selected edges/vertices",
        command="mesh.bevel",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "offset": Float(default=0.1, minimum=0.0, summary="Bevel width"),
            "segments": Int(default=1, minimum=1, maximum=100, summary="Number of bevel segments"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.inset",
        category="mesh",
        summary="Inset the selected faces",
        command="mesh.inset",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "thickness": Float(default=0.1, minimum=0.0, summary="Inset thickness"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.subdivide",
        category="mesh",
        summary="Subdivide the selected edges/faces",
        command="mesh.subdivide",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "cuts": Int(default=1, minimum=1, maximum=100, summary="Number of cuts"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.recalc_normals",
        category="mesh",
        summary="Recalculate the mesh normals consistently",
        command="mesh.recalc_normals",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "inside": Bool(default=False, summary="Point normals inside instead of outside"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.selection_report",
        category="mesh",
        summary="Report selected vertices, edges, and faces",
        command="mesh.selection_report",
        params={
            "object": Str(summary="Mesh object to inspect (defaults to active)"),
        },
    ),
    ToolSpec(
        name="mesh.select_all",
        category="mesh",
        summary="Select, deselect, invert, or toggle all mesh elements",
        command="mesh.select_all",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "action": Enum(SELECT_ALL_ACTIONS, default="SELECT", summary="Select-all action"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.select_by_index",
        category="mesh",
        summary="Select mesh elements by zero-based index",
        command="mesh.select_by_index",
        params={
            "object": Str(required=True, summary="Mesh object to edit"),
            "mode": Enum(MESH_ELEMENT_MODES, required=True, summary="Element mode"),
            "indices": Str(required=True, summary="Comma-separated element indices"),
            "action": Enum(MESH_SELECTION_ACTIONS, default="REPLACE", summary="Selection action"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.delete",
        category="mesh",
        summary="Delete selected mesh elements",
        command="mesh.delete",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "type": Enum(MESH_DELETE_TYPES, default="VERT", summary="Delete mode"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.dissolve",
        category="mesh",
        summary="Dissolve selected mesh elements",
        command="mesh.dissolve",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "type": Enum(MESH_DISSOLVE_TYPES, default="EDGES", summary="Dissolve mode"),
            "use_verts": Bool(default=False, summary="Dissolve connected vertices for edges/faces"),
            "angle_limit": Float(default=0.0872665, minimum=0.0, summary="Limited dissolve angle in radians"),
            "use_dissolve_boundaries": Bool(default=False, summary="Dissolve boundaries in limited mode"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.shade_smooth",
        category="mesh",
        summary="Toggle smooth/flat shading on the object",
        command="mesh.shade_smooth",
        params={
            "object": Str(summary="Mesh object to shade (defaults to active)"),
            "smooth": Bool(default=True, summary="Smooth shading when true, flat when false"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="mesh.report",
        category="mesh",
        summary="Analytic topology report for a mesh (read-only)",
        command="mesh.report",
        params={
            "object": Str(summary="Mesh object to inspect (defaults to active)"),
        },
    ),
]
