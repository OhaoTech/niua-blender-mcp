"""Topology overlay helpers.

Pure grouping is unit-testable without Blender. The bpy-bound render path is added
separately so topology eyes can mark defects with real materials instead of
viewport overlays.
"""

from __future__ import annotations

from typing import Any, Iterable


def face_type_groups(polygons: Iterable[Any]) -> dict:
    """Group polygon indices by side count: tris (3), quads (4), ngons (>4)."""
    tris: list[int] = []
    quads: list[int] = []
    ngons: list[int] = []
    for p in polygons:
        sides = len(p.vertices)
        if sides == 3:
            tris.append(p.index)
        elif sides == 4:
            quads.append(p.index)
        elif sides > 4:
            ngons.append(p.index)
    return {"tris": tris, "quads": quads, "ngons": ngons}
