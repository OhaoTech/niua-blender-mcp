from niua_blender_mcp.evals.harness import run_task

TASK = {
    "id": "modeling_prop",
    "gates": [{"path": "topology.quad_ratio", "op": ">=", "value": 0.95}],
    "judge_threshold": 7.0,
    "rubric": "r",
}


def _obs(quad_ratio):
    return lambda: {"metrics": {"topology": {"quad_ratio": quad_ratio}}, "images": [], "overlays": []}


def test_fails_when_gates_fail():
    card = run_task(TASK, produce=lambda: None, observe=_obs(0.0))
    assert card["gates_pass"] is False
    assert card["pass"] is False
    assert card["judge_score"] == 0.0


def test_passes_when_gates_and_judge_pass():
    from niua_blender_mcp.evals.judge import stub_judge

    card = run_task(
        TASK,
        produce=lambda: None,
        observe=_obs(1.0),
        judge=lambda i, o, r: stub_judge(i, o, r, score=9.0),
    )
    assert card["gates_pass"] is True
    assert card["judge_pass"] is True
    assert card["pass"] is True


def test_gates_pass_but_judge_below_threshold():
    card = run_task(
        TASK,
        produce=lambda: None,
        observe=_obs(1.0),
        judge=lambda i, o, r: {"score": 5.0, "critique": "weak"},
    )
    assert card["gates_pass"] is True
    assert card["pass"] is False
