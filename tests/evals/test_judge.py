from niua_blender_mcp.evals.judge import stub_judge


def test_stub_judge_is_deterministic():
    out = stub_judge([], [], "rubric", score=6.5)
    assert out == {"score": 6.5, "critique": "stub"}
