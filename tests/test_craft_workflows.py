from __future__ import annotations

import pytest

from niua_blender_mcp import craft_workflows as server_workflows
from niua_mcp_bridge.core import craft_workflows as addon_workflows


def test_server_and_addon_craft_workflow_registries_match() -> None:
    server = {workflow["id"]: workflow for workflow in server_workflows.list_workflows()}
    addon = {workflow["id"]: workflow for workflow in addon_workflows.list_workflows()}

    assert sorted(server) == ["hard_surface.panel_detail_pass"]
    assert server == addon


def test_workflow_records_are_returned_as_copies() -> None:
    first = addon_workflows.get_workflow("hard_surface.panel_detail_pass")
    first["default_params"]["width"] = 99

    second = addon_workflows.get_workflow("hard_surface.panel_detail_pass")

    assert second["default_params"]["width"] == 0.02


def test_list_workflows_filters_by_asset_class_and_stage() -> None:
    hard_surface = addon_workflows.list_workflows(asset_class="hard_surface_prop", stage="retopo")
    organic = addon_workflows.list_workflows(asset_class="organic_prop", stage="retopo")
    wrong_stage = addon_workflows.list_workflows(asset_class="hard_surface_prop", stage="uv")

    assert [workflow["id"] for workflow in hard_surface] == ["hard_surface.panel_detail_pass"]
    assert organic == []
    assert wrong_stage == []


def test_recommend_workflows_returns_hard_surface_retopo_match() -> None:
    out = addon_workflows.recommend_workflows(asset_class="hard_surface_prop", stage="retopo")

    assert out["reason"] == "matched asset_class=hard_surface_prop stage=retopo"
    assert [item["id"] for item in out["recommendations"]] == ["hard_surface.panel_detail_pass"]
    assert out["recommendations"][0]["match"] == "asset_class+stage"


def test_recommend_workflows_uses_state_when_explicit_values_are_missing() -> None:
    out = addon_workflows.recommend_workflows(
        state={"asset_class": "hard_surface_prop", "stage": "repair"},
    )

    assert out["reason"] == "matched asset_class=hard_surface_prop stage=repair"
    assert [item["id"] for item in out["recommendations"]] == ["hard_surface.panel_detail_pass"]


def test_recommend_workflows_returns_no_fallback_for_unsupported_class() -> None:
    out = addon_workflows.recommend_workflows(asset_class="organic_prop", stage="retopo")

    assert out == {
        "recommendations": [],
        "reason": "no workflow matched asset_class=organic_prop stage=retopo",
    }


def test_unknown_workflow_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown craft workflow: nope"):
        addon_workflows.get_workflow("nope")
