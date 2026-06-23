from niua_mcp_bridge.core.knowledge import stage_pack
from niua_mcp_bridge.core.self_critique import critique_stage


def test_self_critique_explains_failed_uv_gate():
    gate = {
        "gates_pass": False,
        "gates": [
            {"path": "uv.has_uvs", "op": "==", "value": True, "actual": False, "pass": False},
            {"path": "uv.overlap_detected", "op": "==", "value": False, "actual": False, "pass": True},
        ],
    }

    out = critique_stage("uv", gate, stage_pack("uv"), attempt=1, max_attempts=3)

    assert out["stage"] == "uv"
    assert out["failed_count"] == 1
    assert out["may_retry"] is True
    assert out["failed_gates"][0]["path"] == "uv.has_uvs"
    assert "unwrap" in out["recommendations"][0].lower()


def test_self_critique_blocks_retry_at_budget():
    gate = {"gates_pass": False, "gates": [{"path": "uv.has_uvs", "pass": False}]}

    out = critique_stage("uv", gate, stage_pack("uv"), attempt=3, max_attempts=3)

    assert out["may_retry"] is False
