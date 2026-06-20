from niua_blender_mcp.evals.battery import load_task


def test_loads_modeling_task():
    task = load_task("modeling_prop")
    assert task["id"] == "modeling_prop"
    assert task["competency"] == "modeling"
    assert task["gates"]
    assert "rubric" in task and task["rubric"].strip()
    assert isinstance(task["judge_threshold"], (int, float))


def test_modeling_rubric_has_score_anchors_and_senior_threshold():
    task = load_task("modeling_prop")
    rubric = task["rubric"].lower()
    assert "score anchors" in rubric
    assert "7-8" in rubric
    assert task["judge_threshold"] == 7.0
