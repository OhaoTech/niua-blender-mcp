"""Gate DEFINITIONS live in core/gates.py, independent of any pipeline FSM."""

import pytest

from niua_mcp_bridge.core import gates


def test_gate_profile_maps_stages():
    assert gates.gate_profile("repair") == "orientation"
    assert gates.gate_profile("retopo") == "retopo"
    assert gates.gate_profile("intake") is None
    with pytest.raises(ValueError):
        gates.gate_profile("nonsense")


def test_stage_gates_applies_asset_class_overrides():
    base, applied = gates.stage_gates("retopo")
    assert {g["path"] for g in base} == {
        "topology.quad_ratio", "topology.ngons", "topology.non_manifold_edges"
    }
    assert applied == {}
    organic, applied = gates.stage_gates("retopo", asset_class="organic_prop")
    quad = next(g for g in organic if g["path"] == "topology.quad_ratio")
    assert quad["value"] == 0.85
    assert "retopo" in applied


def test_check_gates_evaluates_paths():
    metrics = {"topology": {"quad_ratio": 0.99, "ngons": 0, "non_manifold_edges": 3}}
    out = gates.check_gates(metrics, gates.stage_gates("retopo")[0])
    assert out["gates_pass"] is False
    by_path = {g["path"]: g for g in out["gates"]}
    assert by_path["topology.quad_ratio"]["pass"] is True
    assert by_path["topology.non_manifold_edges"]["pass"] is False
    assert by_path["topology.non_manifold_edges"]["actual"] == 3


def test_missing_metric_fails_closed():
    out = gates.check_gates({}, gates.stage_gates("uv")[0])
    assert out["gates_pass"] is False
    assert all(g["actual"] is None and g["pass"] is False for g in out["gates"])
