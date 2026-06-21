"""Lattice GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Int, Str, ToolSpec, Vec3

SPECS = [
    ToolSpec(
        name="lattice.create",
        category="lattice",
        summary="Create a lattice object",
        command="lattice.create",
        params={
            "name": Str(default="", summary="Optional object name"),
            "location": Vec3(default=[0, 0, 0], summary="World location"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="lattice.report",
        category="lattice",
        summary="Report lattice object, data, and point state",
        command="lattice.report",
        params={"object": Str(required=True, summary="Lattice object to inspect")},
    ),
    ToolSpec(
        name="lattice.set",
        category="lattice",
        summary="Set one RNA property on lattice data",
        command="lattice.set",
        params={
            "object": Str(required=True, summary="Lattice object to edit"),
            "property": Str(required=True, summary="Lattice data property"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="lattice.point_set",
        category="lattice",
        summary="Set one lattice point's deformed coordinate",
        command="lattice.point_set",
        params={
            "object": Str(required=True, summary="Lattice object to edit"),
            "index": Int(required=True, minimum=0, summary="Lattice point index"),
            "co_deform": Vec3(required=True, summary="New deformed coordinate"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="lattice.convert_to_mesh",
        category="lattice",
        summary="Convert a lattice to a mesh when Blender supports conversion",
        command="lattice.convert_to_mesh",
        params={
            "object": Str(required=True, summary="Lattice object to convert"),
            "name": Str(default="", summary="Optional converted object name"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
