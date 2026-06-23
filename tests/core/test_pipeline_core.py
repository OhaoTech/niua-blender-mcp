import pytest

from niua_mcp_bridge.core import pipeline


def setup_function():
    pipeline.reset()


def _gate(stage: str, passed: bool) -> dict:
    return {
        "stage": stage,
        "gates": [{"path": f"{stage}.ok", "pass": passed}],
        "gates_pass": passed,
    }


def _statuses(out: dict) -> dict:
    return {stage["name"]: stage["status"] for stage in out["stages"]}


def test_stage_registry_declares_game_asset_flow():
    registry = pipeline.stage_registry()

    assert [stage["name"] for stage in registry] == [
        "intake",
        "repair",
        "retopo",
        "uv",
        "material",
        "optimize",
        "export_preflight",
        "exported",
    ]
    assert {stage["name"]: stage["gate_profile"] for stage in registry} == {
        "intake": None,
        "repair": "orientation",
        "retopo": "retopo",
        "uv": "uv",
        "material": None,
        "optimize": "optimize",
        "export_preflight": "export_preflight",
        "exported": None,
    }
    assert registry[-1]["terminal"] is True


def test_start_sets_intake_status_and_checkpoint():
    out = pipeline.start("Hero")

    assert out["object"] == "Hero"
    assert out["state"]["profile"] == "game_asset"
    assert out["state"]["current_stage"] == "intake"
    assert out["state"]["completed"] == []
    assert out["state"]["checkpoints"] == {"intake": "pipeline:intake:entry"}
    assert _statuses(out)["intake"] == "current"
    assert pipeline.status()["runs"][0]["object"] == "Hero"


def test_advance_moves_no_gate_intake_to_repair():
    pipeline.start("Hero")

    out = pipeline.advance("Hero")

    assert out["state"]["current_stage"] == "repair"
    assert out["state"]["completed"] == ["intake"]
    assert out["state"]["checkpoints"]["repair"] == "pipeline:repair:entry"
    assert _statuses(out)["intake"] == "passed"
    assert _statuses(out)["repair"] == "current"


def test_advance_blocks_failed_required_gate():
    pipeline.start("Hero")
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "repair", _gate("repair", False))

    with pytest.raises(ValueError, match="repair"):
        pipeline.advance("Hero")

    out = pipeline.status("Hero")
    assert out["state"]["current_stage"] == "repair"
    assert _statuses(out)["repair"] == "failed"


def test_advance_passes_required_gate_and_records_stage():
    pipeline.start("Hero")
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "repair", _gate("repair", True))

    out = pipeline.advance("Hero")

    assert out["state"]["current_stage"] == "retopo"
    assert out["state"]["completed"] == ["intake", "repair"]
    assert out["state"]["gates"]["repair"]["gates_pass"] is True
    assert _statuses(out)["repair"] == "passed"
    assert _statuses(out)["retopo"] == "current"


def test_rollback_pointer_moves_current_stage_back_and_invalidates_future_gates():
    pipeline.start("Hero")
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "repair", _gate("repair", True))
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "retopo", _gate("retopo", True))
    pipeline.advance("Hero")

    out = pipeline.rollback_pointer("Hero", "repair")

    assert out["state"]["current_stage"] == "repair"
    assert out["state"]["completed"] == ["intake"]
    assert out["state"]["gates"] == {}
    assert out["state"]["checkpoints"]["repair"] == "pipeline:repair:entry"
    assert _statuses(out)["intake"] == "passed"
    assert _statuses(out)["repair"] == "current"
    assert _statuses(out)["retopo"] == "pending"


def test_optimize_stage_requires_engine_readiness_gate_before_export_preflight():
    pipeline.start("Hero")
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "repair", _gate("repair", True))
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "retopo", _gate("retopo", True))
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "uv", _gate("uv", True))
    pipeline.advance("Hero")
    out = pipeline.advance("Hero")

    assert out["state"]["current_stage"] == "optimize"

    with pytest.raises(ValueError, match="optimize"):
        pipeline.advance("Hero")

    pipeline.record_gate("Hero", "optimize", _gate("optimize", True))
    out = pipeline.advance("Hero")

    assert out["state"]["current_stage"] == "export_preflight"
    assert out["state"]["completed"] == ["intake", "repair", "retopo", "uv", "material", "optimize"]
