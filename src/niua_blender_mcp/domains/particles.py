"""Particles GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="particles.systems",
        category="particles",
        summary="List particle systems on an object",
        command="particles.systems",
        params={"object": Str(required=True, summary="Object to inspect")},
    ),
    ToolSpec(
        name="particles.add",
        category="particles",
        summary="Add a particle system to an object",
        command="particles.add",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "name": Str(default="", summary="Optional particle system name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="particles.remove",
        category="particles",
        summary="Remove a named particle system from an object",
        command="particles.remove",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "name": Str(required=True, summary="Particle system name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="particles.report",
        category="particles",
        summary="Report live RNA properties for one or all particle systems",
        command="particles.report",
        params={
            "object": Str(required=True, summary="Object to inspect"),
            "name": Str(default="", summary="Optional particle system name; omit for all"),
        },
    ),
    ToolSpec(
        name="particles.set",
        category="particles",
        summary="Set one RNA property on a particle system or its settings",
        command="particles.set",
        params={
            "object": Str(required=True, summary="Object to edit"),
            "name": Str(required=True, summary="Particle system name"),
            "property": Str(required=True, summary="Property path, e.g. count or settings.frame_start"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
