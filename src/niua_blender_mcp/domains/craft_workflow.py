"""Craft workflow tool manifest."""

from __future__ import annotations

from ..asset_classes import ASSET_CLASS_IDS
from ..craft_workflows import WORKFLOW_IDS
from ..kernel import Enum, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="craft_workflow.list",
        category="craft_workflow",
        summary="List Layer 2 craft workflows, optionally filtered by asset class and stage",
        command="craft_workflow.list",
        params={
            "asset_class": Enum(ASSET_CLASS_IDS, summary="Optional asset-class filter"),
            "stage": Str(summary="Optional pipeline stage filter"),
        },
        mutates=False,
        tier="curated",
    ),
    ToolSpec(
        name="craft_workflow.describe",
        category="craft_workflow",
        summary="Describe one Layer 2 craft workflow",
        command="craft_workflow.describe",
        params={
            "workflow": Enum(WORKFLOW_IDS, required=True, summary="Craft workflow id"),
        },
        mutates=False,
        tier="curated",
    ),
    ToolSpec(
        name="craft_workflow.recommend",
        category="craft_workflow",
        summary="Recommend craft workflows for an asset class and pipeline stage",
        command="craft_workflow.recommend",
        params={
            "object": Str(summary="Optional object whose pipeline state can supply asset class and stage"),
            "asset_class": Enum(ASSET_CLASS_IDS, summary="Optional asset-class override"),
            "stage": Str(summary="Optional pipeline stage override"),
        },
        mutates=False,
        tier="curated",
    ),
]
