import pytest

from niua_blender_mcp.evals.gates import check_gates
from niua_blender_mcp.evals.stage_gates import stage_gates


def test_uv_stage_gates_pass_clean_metrics():
    metrics = {
        "uv": {
            "has_uvs": True,
            "out_of_bounds_loops": 0,
            "overlap_detected": False,
            "stretch_ratio": 1.2,
        }
    }
    assert check_gates(metrics, stage_gates("uv"))["gates_pass"] is True


def test_optimize_stage_gates_pass_engine_ready_metrics():
    metrics = {
        "engine": {
            "within_triangle_budget": True,
            "within_material_budget": True,
            "within_texture_budget": True,
            "has_lods": True,
            "has_collision_proxy": True,
        }
    }

    out = check_gates(metrics, stage_gates("optimize"))

    assert out["gates_pass"] is True
    assert [gate["path"] for gate in out["gates"]] == [
        "engine.within_triangle_budget",
        "engine.within_material_budget",
        "engine.within_texture_budget",
        "engine.has_lods",
        "engine.has_collision_proxy",
    ]


def test_unknown_stage_raises_key_error():
    with pytest.raises(KeyError, match="nope"):
        stage_gates("nope")
