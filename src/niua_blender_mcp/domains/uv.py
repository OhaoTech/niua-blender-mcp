"""UV domain manifest: unwrapping and island layout.

All projection/unwrap operators run in EDIT mode on the active mesh object's
selection; the kernel context resolver guarantees EDIT mode + a mesh active object
+ a selection before they run, and these handlers select-all-faces so the projection
covers the whole mesh. ``uv.report`` is read-only analytic feedback ("the eyes"):
UV layer names, whether the mesh has UVs, and a cheap island count.
"""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="uv.layers",
        category="uv",
        summary="List UV layers and active UV layer",
        command="uv.layers",
        params={"object": Str(summary="Mesh object to inspect (defaults to active)")},
    ),
    ToolSpec(
        name="uv.layer_create",
        category="uv",
        summary="Create a UV layer",
        command="uv.layer_create",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "name": Str(default="UVMap", summary="UV layer name"),
            "do_init": Bool(default=True, summary="Initialize from existing UVs"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.layer_set_active",
        category="uv",
        summary="Set the active UV layer by name",
        command="uv.layer_set_active",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "name": Str(required=True, summary="UV layer name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.layer_delete",
        category="uv",
        summary="Delete a UV layer by name",
        command="uv.layer_delete",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "name": Str(required=True, summary="UV layer name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.seams",
        category="uv",
        summary="Report seam edge indices",
        command="uv.seams",
        params={"object": Str(summary="Mesh object to inspect (defaults to active)")},
    ),
    ToolSpec(
        name="uv.set_seams",
        category="uv",
        summary="Set, add, remove, or clear seam edge flags",
        command="uv.set_seams",
        params={
            "object": Str(summary="Mesh object to edit (defaults to active)"),
            "edges": Str(default="", summary="Comma-separated edge indices"),
            "action": Enum(["SET", "ADD", "REMOVE", "CLEAR"], default="SET", summary="Seam mutation action"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.export_layout",
        category="uv",
        summary="Export the mesh UV layout as an image file",
        command="uv.export_layout",
        params={
            "object": Str(summary="Mesh object to export (defaults to active)"),
            "path": Str(required=True, summary="Destination image path"),
            "size": Int(default=1024, minimum=1, maximum=16384, summary="Square output size in pixels"),
            "opacity": Float(default=0.25, minimum=0.0, maximum=1.0, summary="Face fill opacity"),
            "export_all": Bool(default=True, summary="Export all UVs, not just selected faces"),
            "modified": Bool(default=False, summary="Export UVs after modifiers"),
            "format": Enum(["AUTO", "PNG", "SVG", "EPS"], default="AUTO", summary="Output file format"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.smart_unwrap",
        category="uv",
        summary="Smart UV project the selected faces (angle-based auto seams)",
        command="uv.smart_unwrap",
        params={
            "object": Str(summary="Mesh object to unwrap (defaults to active)"),
            "angle_limit": Float(
                default=66.0,
                minimum=0.0,
                maximum=89.0,
                summary="Angle limit in degrees for splitting islands",
            ),
            "island_margin": Float(
                default=0.0,
                minimum=0.0,
                maximum=1.0,
                summary="Margin between islands in UV space",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.unwrap",
        category="uv",
        summary="Unwrap the selected faces along existing seams",
        command="uv.unwrap",
        params={
            "object": Str(summary="Mesh object to unwrap (defaults to active)"),
            "method": Enum(
                ["ANGLE_BASED", "CONFORMAL"],
                default="ANGLE_BASED",
                summary="Unwrapping algorithm",
            ),
            "island_margin": Float(
                default=0.0,
                minimum=0.0,
                maximum=1.0,
                summary="Margin between islands in UV space",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.cube_project",
        category="uv",
        summary="Cube-project the selected faces onto the UV map",
        command="uv.cube_project",
        params={
            "object": Str(summary="Mesh object to project (defaults to active)"),
            "cube_size": Float(default=1.0, minimum=0.0, summary="Size of the projection cube"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.sphere_project",
        category="uv",
        summary="Sphere-project the selected faces onto the UV map",
        command="uv.sphere_project",
        params={
            "object": Str(summary="Mesh object to project (defaults to active)"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.pack_islands",
        category="uv",
        summary="Pack the UV islands to fit the [0,1] UV space",
        command="uv.pack_islands",
        params={
            "object": Str(summary="Mesh object whose islands to pack (defaults to active)"),
            "margin": Float(
                default=0.001,
                minimum=0.0,
                maximum=1.0,
                summary="Space between packed islands in UV space",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.average_islands_scale",
        category="uv",
        summary="Average the texel density / scale of all UV islands",
        command="uv.average_islands_scale",
        params={
            "object": Str(summary="Mesh object whose islands to scale (defaults to active)"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="uv.report",
        category="uv",
        summary="Analytic UV report for a mesh: layers, has_uvs, island count (read-only)",
        command="uv.report",
        params={
            "object": Str(summary="Mesh object to inspect (defaults to active)"),
        },
    ),
]
