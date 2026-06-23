"""Layer 2 game-asset pipeline state store."""

from __future__ import annotations

from copy import deepcopy
import operator
from typing import Any

_STAGES = [
    {"name": "intake", "gate_profile": None, "terminal": False},
    {"name": "repair", "gate_profile": "orientation", "terminal": False},
    {"name": "retopo", "gate_profile": "retopo", "terminal": False},
    {"name": "uv", "gate_profile": "uv", "terminal": False},
    {"name": "bake", "gate_profile": "bake", "terminal": False},
    {"name": "material", "gate_profile": "material", "terminal": False},
    {"name": "optimize", "gate_profile": "optimize", "terminal": False},
    {"name": "export_preflight", "gate_profile": "export_preflight", "terminal": False},
    {"name": "exported", "gate_profile": None, "terminal": True},
]
_STAGE_INDEX = {stage["name"]: index for index, stage in enumerate(_STAGES)}
_STORE: dict[str, dict[str, Any]] = {}
_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "<": operator.lt, ">": operator.gt}
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


def _checkpoint_label(stage: str) -> str:
    return f"pipeline:{stage}:entry"


def _require_stage(stage: str) -> None:
    if stage not in _STAGE_INDEX:
        raise ValueError(f"unknown pipeline stage: {stage}")


def _require_state(object_name: str) -> dict[str, Any]:
    try:
        return _STORE[object_name]
    except KeyError as exc:
        raise ValueError(f"pipeline has not started for object: {object_name}") from exc


def _stage_status(state: dict[str, Any], stage: dict[str, Any]) -> str:
    name = stage["name"]
    if state["complete"] and stage["terminal"]:
        return "complete"
    if name in state["completed"]:
        return "passed"
    if name == state["current_stage"]:
        gate = state["gates"].get(name)
        if gate is not None and not gate.get("gates_pass", False):
            return "failed"
        return "current"
    return "pending"


def _status_for_state(state: dict[str, Any]) -> dict[str, Any]:
    state_copy = deepcopy(state)
    return {
        "object": state["object"],
        "state": state_copy,
        "stages": [
            {
                **deepcopy(stage),
                "status": _stage_status(state, stage),
                "gate": deepcopy(state["gates"].get(stage["name"])),
                "checkpoint": state["checkpoints"].get(stage["name"]),
            }
            for stage in _STAGES
        ],
    }


def stage_registry() -> list[dict[str, Any]]:
    return [deepcopy(stage) for stage in _STAGES]


def gate_profile(stage: str) -> str | None:
    _require_stage(stage)
    return _STAGES[_STAGE_INDEX[stage]]["gate_profile"]


def stage_gates(stage: str) -> list[dict[str, Any]]:
    profile = gate_profile(stage)
    if profile is None:
        return []
    try:
        return [deepcopy(gate) for gate in _GATES[profile]]
    except KeyError as exc:
        raise ValueError(f"unknown stage gate profile: {profile}") from exc


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


def start(object_name: str, profile: str = "game_asset") -> dict[str, Any]:
    state = {
        "object": object_name,
        "profile": profile,
        "current_stage": "intake",
        "completed": [],
        "complete": False,
        "gates": {},
        "checkpoints": {"intake": _checkpoint_label("intake")},
    }
    _STORE[object_name] = state
    return status(object_name)


def get_state(object_name: str) -> dict[str, Any] | None:
    state = _STORE.get(object_name)
    return deepcopy(state) if state is not None else None


def status(object_name: str | None = None) -> dict[str, Any]:
    if object_name is None:
        return {"runs": [_status_for_state(_STORE[name]) for name in sorted(_STORE)]}
    state = _STORE.get(object_name)
    if state is None:
        return {"object": object_name, "state": None, "stages": stage_registry()}
    return _status_for_state(state)


def record_gate(object_name: str, stage: str, gate: dict[str, Any]) -> dict[str, Any]:
    _require_stage(stage)
    state = _require_state(object_name)
    gate_copy = deepcopy(gate)
    gate_copy.setdefault("stage", stage)
    state["gates"][stage] = gate_copy
    return status(object_name)


def advance(object_name: str) -> dict[str, Any]:
    state = _require_state(object_name)
    current_stage = state["current_stage"]
    current_index = _STAGE_INDEX[current_stage]
    current_def = _STAGES[current_index]
    if current_def["terminal"]:
        state["complete"] = True
        return status(object_name)

    if current_def["gate_profile"] is not None:
        gate = state["gates"].get(current_stage)
        if gate is None or not gate.get("gates_pass", False):
            raise ValueError(f"stage gates have not passed: {current_stage}")

    if current_stage not in state["completed"]:
        state["completed"].append(current_stage)
    next_stage = _STAGES[current_index + 1]["name"]
    state["current_stage"] = next_stage
    state["checkpoints"].setdefault(next_stage, _checkpoint_label(next_stage))
    state["complete"] = _STAGES[current_index + 1]["terminal"]
    return status(object_name)


def rollback_pointer(object_name: str, stage: str) -> dict[str, Any]:
    _require_stage(stage)
    state = _require_state(object_name)
    if stage not in state["checkpoints"]:
        raise ValueError(f"pipeline checkpoint does not exist for stage: {stage}")

    target_index = _STAGE_INDEX[stage]
    state["current_stage"] = stage
    state["complete"] = False
    state["completed"] = [
        completed for completed in state["completed"] if _STAGE_INDEX[completed] < target_index
    ]
    state["gates"] = {
        gate_stage: gate
        for gate_stage, gate in state["gates"].items()
        if _STAGE_INDEX[gate_stage] < target_index
    }
    return status(object_name)


def reset() -> None:
    _STORE.clear()
