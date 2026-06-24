"""Layer 2 craft workflow registry for deterministic server-side workflow choices."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_WORKFLOWS: dict[str, dict[str, Any]] = {
    "hard_surface.panel_detail_pass": {
        "id": "hard_surface.panel_detail_pass",
        "label": "Hard-surface panel detail pass",
        "asset_class": "hard_surface_prop",
        "stages": ["repair", "retopo"],
        "summary": "Add readable hard-surface panel recesses, chamfer sharp edges, and normalize topology.",
        "required_tools": [
            "model.recess_panels",
            "model.bevel_edges",
            "model.retopo_quads",
        ],
        "default_params": {
            "inset": 0.08,
            "depth": 0.04,
            "angle": 30.0,
            "width": 0.02,
            "segments": 2,
            "face_threshold": 40.0,
        },
        "gate_targets": ["topology.ngons", "topology.quad_ratio", "topology.non_manifold_edges"],
        "recipe_steps": [
            "recess broad faces into readable panel detail",
            "bevel sharp edges with a small support chamfer",
            "normalize topology back toward quads and consistent normals",
        ],
        "outputs": ["panel recesses", "edge chamfers", "quad-normalized topology"],
        "cautions": [
            "Run on a copied/checkpointed mesh when preserving the original silhouette matters.",
            "Re-check topology gates after the pass; beveling and inset operations can create extra poles.",
        ],
    },
}

WORKFLOW_IDS = sorted(_WORKFLOWS)


def list_workflows(asset_class: str | None = None, stage: str | None = None) -> list[dict[str, Any]]:
    workflows = [deepcopy(_WORKFLOWS[name]) for name in WORKFLOW_IDS]
    if asset_class:
        workflows = [workflow for workflow in workflows if workflow["asset_class"] == asset_class]
    if stage:
        workflows = [workflow for workflow in workflows if stage in workflow["stages"]]
    return workflows


def get_workflow(workflow_id: str) -> dict[str, Any]:
    try:
        return deepcopy(_WORKFLOWS[workflow_id])
    except KeyError as exc:
        raise KeyError(f"unknown craft workflow: {workflow_id}") from exc


def _resolve_target(
    asset_class: str | None,
    stage: str | None,
    state: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    resolved_asset_class = asset_class
    resolved_stage = stage
    if state is not None:
        if not resolved_asset_class and isinstance(state.get("asset_class"), str):
            resolved_asset_class = state["asset_class"]
        if not resolved_stage and isinstance(state.get("current_stage"), str):
            resolved_stage = state["current_stage"]
        if not resolved_stage and isinstance(state.get("stage"), str):
            resolved_stage = state["stage"]
    return resolved_asset_class, resolved_stage


def _recommendation(workflow: dict[str, Any], match: str) -> dict[str, Any]:
    out = {
        "id": workflow["id"],
        "label": workflow["label"],
        "asset_class": workflow["asset_class"],
        "stages": deepcopy(workflow["stages"]),
        "summary": workflow["summary"],
        "required_tools": deepcopy(workflow["required_tools"]),
        "match": match,
    }
    return out


def recommend_workflows(
    asset_class: str | None = None,
    stage: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_asset_class, resolved_stage = _resolve_target(asset_class, stage, state)
    matches: list[dict[str, Any]] = []
    if resolved_asset_class and resolved_stage:
        matches = [
            _recommendation(workflow, "asset_class+stage")
            for workflow in list_workflows(resolved_asset_class, resolved_stage)
        ]
    if not matches and resolved_asset_class:
        matches = [
            _recommendation(workflow, "asset_class")
            for workflow in list_workflows(asset_class=resolved_asset_class)
        ]
    target = f"asset_class={resolved_asset_class or '*'} stage={resolved_stage or '*'}"
    if matches:
        return {"recommendations": matches, "reason": f"matched {target}"}
    return {"recommendations": [], "reason": f"no workflow matched {target}"}
