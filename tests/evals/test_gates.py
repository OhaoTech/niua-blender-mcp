from niua_blender_mcp.evals.gates import check_gates

METRICS = {"topology": {"quad_ratio": 1.0, "ngons": 0, "non_manifold_edges": 0, "pole_count": 8}}


def test_all_gates_pass():
    gates = [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.95},
        {"path": "topology.ngons", "op": "==", "value": 0},
    ]
    out = check_gates(METRICS, gates)
    assert out["gates_pass"] is True
    assert all(g["pass"] for g in out["gates"])


def test_failing_gate_blocks():
    gates = [{"path": "topology.pole_count", "op": "<=", "value": 4}]
    out = check_gates(METRICS, gates)
    assert out["gates_pass"] is False
    assert out["gates"][0]["actual"] == 8


def test_missing_path_fails_safe():
    out = check_gates(METRICS, [{"path": "uv.texel_density", "op": ">=", "value": 100}])
    assert out["gates_pass"] is False
    assert out["gates"][0]["actual"] is None
