"""Grounded Layer 2 stage knowledge packs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_PACKS: dict[str, dict[str, Any]] = {
    "repair": {
        "stage": "repair",
        "standards": "Repair stage validates applied transforms, non-degenerate faces, and outward-facing normals before topology work.",
        "targets": {"degenerate_faces": 0, "inward_facing_faces": 0},
        "sources": [
            {"title": "Blender Manual - Mesh Normals", "locator": "manual/modeling/meshes/editing/mesh/normals"}
        ],
        "recommendations": {
            "orientation.degenerate_faces": "Remove zero-area faces or merge duplicate vertices, then recalculate normals.",
            "orientation.inward_facing_faces": "Run outward normal recalculation and inspect backface orientation.",
        },
    },
    "retopo": {
        "stage": "retopo",
        "standards": "Game prop retopo should favor clean quads, zero n-gons, and manifold surfaces before UV work.",
        "targets": {"quad_ratio_min": 0.95, "ngons": 0, "non_manifold_edges": 0},
        "sources": [
            {"title": "Blender Manual - Mesh Cleanup", "locator": "manual/modeling/meshes/editing/mesh/cleanup"}
        ],
        "recommendations": {
            "topology.quad_ratio": "Retopologize large triangle/ngon regions into quads before advancing.",
            "topology.ngons": "Split n-gons into quads or triangles with controlled edge flow.",
            "topology.non_manifold_edges": "Close holes, remove duplicate faces, or repair border edges.",
        },
    },
    "uv": {
        "stage": "uv",
        "standards": "UVs must exist, keep texel density consistent, stay in 0..1 unless intentionally tiled, avoid overlaps, and keep stretch within the stage target.",
        "targets": {
            "has_uvs": True,
            "overlap_detected": False,
            "out_of_bounds_loops": 0,
            "stretch_ratio_max": 2.0,
        },
        "sources": [{"title": "Blender Manual - UV Editing", "locator": "manual/modeling/meshes/uv"}],
        "recommendations": {
            "uv.has_uvs": "Create a UV layer, unwrap all faces, and pack islands.",
            "uv.out_of_bounds_loops": "Pack islands back into the 0..1 tile or document intentional tiling.",
            "uv.overlap_detected": "Separate overlapping islands and repack with margin.",
            "uv.stretch_ratio": "Add seams or use average island scale before repacking.",
        },
    },
    "export_preflight": {
        "stage": "export_preflight",
        "standards": "Before export, transforms must be applied and the mesh must remain manifold for downstream engines.",
        "targets": {"transform_applied": True, "non_manifold_edges": 0},
        "sources": [{"title": "glTF 2.0 Asset Workflow", "locator": "Khronos glTF 2.0 overview"}],
        "recommendations": {
            "scale.transform_applied": "Apply object transforms before export.",
            "topology.non_manifold_edges": "Repair manifold errors before exporting.",
        },
    },
}


def list_packs() -> list[str]:
    return sorted(_PACKS)


def load_pack(name: str) -> dict[str, Any]:
    try:
        return deepcopy(_PACKS[name])
    except KeyError as exc:
        raise KeyError(f"unknown knowledge pack: {name}") from exc


def stage_pack(stage: str) -> dict[str, Any]:
    return load_pack(stage)
