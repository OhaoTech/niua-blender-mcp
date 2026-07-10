"""Objective gate DEFINITIONS: the order-free numeric contract for game-readiness.

This is the load-bearing organ extracted from the deleted pipeline FSM (architecture
audit §2: "KEEP + PROMOTE"). `feedback.readiness` aggregates these groups in NO order;
nothing here stores state, sequences stages, or blocks anything.
"""

from __future__ import annotations

from copy import deepcopy
import operator
from typing import Any

from . import asset_classes

_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "<": operator.lt, ">": operator.gt}

#: Gate-group name -> gate-profile name (None = no objective gates for that group).
GATE_PROFILE_BY_STAGE: dict[str, str | None] = {
    "intake": None,
    "repair": "orientation",
    "retopo": "retopo",
    "uv": "uv",
    "bake": "bake",
    "material": "material",
    "optimize": "optimize",
    "export_preflight": "export_preflight",
    "exported": None,
}

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
        {"path": "engine.lod_triangle_reduction_ok", "op": "==", "value": True},
        {"path": "engine.lod_silhouette_preserved", "op": "==", "value": True},
        {"path": "engine.has_collision_hulls", "op": "==", "value": True},
        {"path": "engine.collision_bounds_valid", "op": "==", "value": True},
    ],
    "export_preflight": [
        {"path": "scale.transform_applied", "op": "==", "value": True},
        {"path": "topology.non_manifold_edges", "op": "==", "value": 0},
        {"path": "export_profile.profile_pass", "op": "==", "value": True},
    ],
}


def gate_profile(stage: str) -> str | None:
    try:
        return GATE_PROFILE_BY_STAGE[stage]
    except KeyError as exc:
        raise ValueError(f"unknown pipeline stage: {stage}") from exc


def stage_gates(stage: str, asset_class: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile = gate_profile(stage)
    if profile is None:
        return [], {}
    try:
        base = [deepcopy(gate) for gate in _GATES[profile]]
    except KeyError as exc:
        raise ValueError(f"unknown stage gate profile: {profile}") from exc
    asset_profile = asset_classes.get_asset_class(asset_class)
    return asset_classes.apply_gate_overrides(base, asset_profile, stage)


def _dig(metrics: dict[str, Any], path: str) -> Any:
    cur: Any = metrics
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def check_gates(metrics: dict[str, Any], gates: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    all_pass = True
    for gate in gates:
        actual = _dig(metrics, gate["path"])
        fn = _OPS.get(gate["op"])
        ok = bool(actual is not None and fn is not None and fn(actual, gate["value"]))
        all_pass = all_pass and ok
        results.append(
            {
                "path": gate["path"],
                "op": gate["op"],
                "value": gate["value"],
                "actual": actual,
                "pass": ok,
            }
        )
    return {"gates": results, "gates_pass": all_pass}
