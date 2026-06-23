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
    "bake": {
        "stage": "bake",
        "standards": "Bake stage requires normal, AO, and cavity map outputs, with data maps stored as Non-Color images before material production advances.",
        "targets": {"bake_maps_present": True, "data_maps_non_color": True},
        "sources": [
            {"title": "Blender Manual - Cycles Baking", "locator": "manual/render/cycles/baking"},
            {"title": "Blender Manual - Color Management", "locator": "manual/render/color_management"},
        ],
        "recommendations": {
            "material.bake_maps_present": "Create or bake NORMAL, AO, and CAVITY texture slots before advancing.",
            "material.data_maps_non_color": "Set normal, roughness, AO, and cavity images to Non-Color data.",
        },
    },
    "material": {
        "stage": "material",
        "standards": "Material production requires a complete PBR texture set and atlas-ready image dimensions before optimization.",
        "targets": {
            "pbr_maps_present": True,
            "textures_within_size": True,
            "atlas_ready": True,
        },
        "sources": [
            {"title": "Khronos glTF 2.0 Materials", "locator": "Khronos glTF material model"},
            {"title": "Blender Manual - Shader Nodes", "locator": "manual/render/shader_nodes"},
        ],
        "recommendations": {
            "material.pbr_maps_present": "Prepare BASE_COLOR, NORMAL, ROUGHNESS, AO, and CAVITY map slots.",
            "material.textures_within_size": "Resize or regenerate oversized textures to the stage texture limit.",
            "material.atlas_ready": "Use complete square PBR textures with data maps in Non-Color space.",
        },
    },
    "optimize": {
        "stage": "optimize",
        "standards": "Optimize validates universal game-engine readiness: triangle, material, and texture budgets plus at least one LOD and a collision proxy.",
        "targets": {
            "within_triangle_budget": True,
            "within_material_budget": True,
            "within_texture_budget": True,
            "has_lods": True,
            "has_collision_proxy": True,
        },
        "sources": [
            {"title": "Khronos glTF Asset Pipeline", "locator": "Khronos glTF asset workflow"},
            {"title": "Blender Manual - Decimate Modifier", "locator": "manual/modeling/modifiers/generate/decimate"},
        ],
        "recommendations": {
            "engine.within_triangle_budget": "Reduce geometry, add a decimated LOD, or raise the explicit budget only if the asset class requires it.",
            "engine.within_material_budget": "Merge material slots or atlas trim/detail materials before export.",
            "engine.within_texture_budget": "Reuse texture images or atlas maps so the asset stays inside the texture budget.",
            "engine.has_lods": "Create at least one named LOD variant such as Asset_LOD1.",
            "engine.has_collision_proxy": "Create a simple named collision proxy such as Asset_COL or UCX_Asset_00.",
        },
    },
    "export_preflight": {
        "stage": "export_preflight",
        "standards": "Before export, transforms must be applied, the mesh must remain manifold, and the selected export profile must pass.",
        "targets": {"transform_applied": True, "non_manifold_edges": 0, "profile_pass": True},
        "sources": [{"title": "glTF 2.0 Asset Workflow", "locator": "Khronos glTF 2.0 overview"}],
        "recommendations": {
            "scale.transform_applied": "Apply object transforms before export.",
            "topology.non_manifold_edges": "Repair manifold errors before exporting.",
            "export_profile.profile_pass": "Run io.profile_validate for the selected profile and fix failed format, naming, axis, LOD, or collision checks.",
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
