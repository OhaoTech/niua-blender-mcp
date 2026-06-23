"""Reusable deterministic gate profiles for Layer 2 stages."""

from __future__ import annotations

_GATES = {
    "retopo": [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.95},
        {"path": "topology.ngons", "op": "==", "value": 0},
        {"path": "topology.non_manifold_edges", "op": "==", "value": 0},
    ],
    "uv": [
        {"path": "uv.has_uvs", "op": "==", "value": True},
        {"path": "uv.out_of_bounds_loops", "op": "==", "value": 0},
        {"path": "uv.overlap_detected", "op": "==", "value": False},
        {"path": "uv.stretch_ratio", "op": "<=", "value": 2.0},
    ],
    "orientation": [
        {"path": "orientation.degenerate_faces", "op": "==", "value": 0},
        {"path": "orientation.inward_facing_faces", "op": "==", "value": 0},
    ],
    "bake": [
        {"path": "material.bake_maps_present", "op": "==", "value": True},
        {"path": "material.data_maps_non_color", "op": "==", "value": True},
    ],
    "material": [
        {"path": "material.pbr_maps_present", "op": "==", "value": True},
        {"path": "material.textures_within_size", "op": "==", "value": True},
        {"path": "material.atlas_ready", "op": "==", "value": True},
    ],
    "optimize": [
        {"path": "engine.within_triangle_budget", "op": "==", "value": True},
        {"path": "engine.within_material_budget", "op": "==", "value": True},
        {"path": "engine.within_texture_budget", "op": "==", "value": True},
        {"path": "engine.has_lods", "op": "==", "value": True},
        {"path": "engine.has_collision_proxy", "op": "==", "value": True},
    ],
    "export_preflight": [
        {"path": "scale.transform_applied", "op": "==", "value": True},
        {"path": "topology.non_manifold_edges", "op": "==", "value": 0},
        {"path": "export_profile.profile_pass", "op": "==", "value": True},
    ],
}


def stage_gates(stage: str) -> list[dict]:
    try:
        return [dict(gate) for gate in _GATES[stage]]
    except KeyError as exc:
        raise KeyError(f"unknown stage gate profile: {stage}") from exc
