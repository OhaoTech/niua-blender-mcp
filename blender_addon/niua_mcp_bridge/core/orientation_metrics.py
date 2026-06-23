"""Normal and orientation quality metrics for Layer 2 gates."""

from __future__ import annotations

import math
from typing import Any


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float] | None:
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length <= 1e-12:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def normal_consistency(normals: list[tuple[float, float, float]]) -> float | None:
    units = [unit for normal in normals if (unit := _unit(normal)) is not None]
    if not units:
        return None
    ref = units[0]
    aligned = sum(1 for n in units if (n[0] * ref[0] + n[1] * ref[1] + n[2] * ref[2]) >= 0.0)
    opposed = len(units) - aligned
    return abs(aligned - opposed) / len(units)


def orientation_quality(obj: Any) -> dict:
    out = {
        "degenerate_faces": None,
        "inward_facing_faces": None,
        "inward_facing_ratio": None,
        "normal_consistency": None,
    }
    try:
        import bmesh  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - fake-bpy and server envs do not have bmesh
        return out

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        faces = list(bm.faces)
        verts = list(bm.verts)
        normals = [(float(f.normal.x), float(f.normal.y), float(f.normal.z)) for f in faces]
        degenerate = sum(1 for f in faces if float(f.calc_area()) <= 1e-12)

        inward = None
        if verts and faces:
            center = sum((v.co for v in verts), verts[0].co * 0.0) / len(verts)
            inward = 0
            for face in faces:
                direction = face.calc_center_median() - center
                if face.normal.dot(direction) < 0.0:
                    inward += 1

        return {
            "degenerate_faces": degenerate,
            "inward_facing_faces": inward,
            "inward_facing_ratio": (inward / len(faces)) if inward is not None and faces else None,
            "normal_consistency": normal_consistency(normals),
        }
    finally:
        bm.free()
