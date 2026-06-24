"""Craft workflow command handlers."""

from __future__ import annotations

from ..context import Ctx
from ..core import craft_workflows
from ..core import pipeline as pipeline_store
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError


def _summary(workflow: dict) -> dict:
    return {
        "id": workflow["id"],
        "label": workflow["label"],
        "asset_class": workflow["asset_class"],
        "stages": list(workflow["stages"]),
        "summary": workflow["summary"],
        "required_tools": list(workflow["required_tools"]),
    }


def list_workflows(ctx: Ctx, payload: dict) -> dict:
    asset_class = payload.get("asset_class")
    stage = payload.get("stage")
    asset_class = asset_class if isinstance(asset_class, str) and asset_class else None
    stage = stage if isinstance(stage, str) and stage else None
    return {
        "workflows": [
            _summary(workflow)
            for workflow in craft_workflows.list_workflows(asset_class=asset_class, stage=stage)
        ]
    }


def describe(ctx: Ctx, payload: dict) -> dict:
    workflow_id = payload.get("workflow")
    if not isinstance(workflow_id, str) or not workflow_id:
        raise BridgeError(INVALID_PARAMS, "workflow is required")
    try:
        return {"workflow": craft_workflows.get_workflow(workflow_id)}
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc


def recommend(ctx: Ctx, payload: dict) -> dict:
    object_name = payload.get("object")
    object_name = object_name if isinstance(object_name, str) and object_name else None
    state = pipeline_store.get_state(object_name) if object_name else None
    asset_class = payload.get("asset_class")
    stage = payload.get("stage")
    return craft_workflows.recommend_workflows(
        asset_class=asset_class if isinstance(asset_class, str) and asset_class else None,
        stage=stage if isinstance(stage, str) and stage else None,
        state=state,
    )


COMMANDS = [
    Command("craft_workflow.list", list_workflows, mutates=False),
    Command("craft_workflow.describe", describe, mutates=False),
    Command("craft_workflow.recommend", recommend, mutates=False),
]
