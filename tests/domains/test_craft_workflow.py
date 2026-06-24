from __future__ import annotations

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.core import pipeline as pipeline_store
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


class FakeBpy:
    pass


def _dispatch(command: str, payload: dict | None = None) -> dict:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()
    return dispatch_on_main(reg, command, payload or {}, ctx)


def test_craft_workflow_tools_registered() -> None:
    names = {spec.name for spec in build_router().specs()}
    reg = build_default_registry()

    for name in ("craft_workflow.list", "craft_workflow.describe", "craft_workflow.recommend"):
        assert name in names
        command = reg.get(name)
        assert command is not None
        assert command.mutates is False


def test_craft_workflow_list_includes_wave9b_workflows() -> None:
    generated = _dispatch("craft_workflow.list", {"asset_class": "generated_cleanup", "stage": "retopo"})
    organic = _dispatch("craft_workflow.list", {"asset_class": "organic_prop", "stage": "retopo"})

    assert [workflow["id"] for workflow in generated["workflows"]] == ["generated_cleanup.rebuild_noisy_mesh"]
    assert [workflow["id"] for workflow in organic["workflows"]] == ["organic.silhouette_retopo_prep"]

    workflow = generated["workflows"][0]
    assert set(workflow) == {
        "id",
        "label",
        "asset_class",
        "stages",
        "summary",
        "required_tools",
    }
    assert workflow["id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert workflow["label"] == "Generated cleanup rebuild noisy mesh"
    assert workflow["asset_class"] == "generated_cleanup"
    assert workflow["stages"] == ["repair", "retopo"]
    assert workflow["summary"] == (
        "Remove common generated-mesh noise, normalize normals, merge duplicates, and rebuild compatible quads."
    )
    assert workflow["required_tools"] == [
        "model.generated_cleanup_pass",
        "model.retopo_quads",
        "feedback.topology",
    ]
    assert "default_params" not in workflow
    assert "gate_targets" not in workflow
    assert "recipe_steps" not in workflow
    assert "outputs" not in workflow
    assert "cautions" not in workflow


def test_craft_workflow_describe_returns_complete_record() -> None:
    out = _dispatch("craft_workflow.describe", {"workflow": "hard_surface.panel_detail_pass"})

    workflow = out["workflow"]
    assert workflow["id"] == "hard_surface.panel_detail_pass"
    assert workflow["asset_class"] == "hard_surface_prop"
    assert workflow["default_params"]["width"] == 0.02
    assert workflow["gate_targets"] == [
        "topology.ngons",
        "topology.quad_ratio",
        "topology.non_manifold_edges",
    ]


def test_craft_workflow_describe_unknown_id_fails_cleanly() -> None:
    with pytest.raises(BridgeError) as exc:
        _dispatch("craft_workflow.describe", {"workflow": "nope"})

    assert exc.value.code == INVALID_PARAMS
    assert "unknown craft workflow: nope" in str(exc.value)


def test_craft_workflow_recommend_returns_wave9b_ranks() -> None:
    generated = _dispatch("craft_workflow.recommend", {"asset_class": "generated_cleanup", "stage": "retopo"})
    organic = _dispatch("craft_workflow.recommend", {"asset_class": "organic_prop", "stage": "retopo"})

    assert generated["recommendations"][0]["id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert generated["recommendations"][0]["rank"] == 1
    assert organic["recommendations"][0]["id"] == "organic.silhouette_retopo_prep"
    assert organic["recommendations"][0]["rank"] == 1


def test_craft_workflow_recommend_returns_no_fallback_for_unsupported_class() -> None:
    out = _dispatch("craft_workflow.recommend", {"asset_class": "from_scratch_prop", "stage": "retopo"})

    assert out == {
        "recommendations": [],
        "reason": "no workflow matched asset_class=from_scratch_prop stage=retopo",
    }


def test_craft_workflow_recommend_uses_pipeline_state() -> None:
    pipeline_store.reset()
    pipeline_store.start("Cube", asset_class="hard_surface_prop", profile_version=1)
    pipeline_store.advance("Cube")

    out = _dispatch("craft_workflow.recommend", {"object": "Cube"})

    assert out["reason"] == "matched asset_class=hard_surface_prop stage=repair"
    assert [item["id"] for item in out["recommendations"]] == ["hard_surface.panel_detail_pass"]
