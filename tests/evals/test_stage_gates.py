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


def test_unknown_stage_raises_key_error():
    with pytest.raises(KeyError, match="nope"):
        stage_gates("nope")
