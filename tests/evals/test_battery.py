from niua_blender_mcp.evals.battery import load_task


def test_loads_modeling_task():
    task = load_task("modeling_prop")
    assert task["id"] == "modeling_prop"
    assert task["competency"] == "modeling"
    assert task["gates"]
    assert "rubric" in task and task["rubric"].strip()
    assert isinstance(task["judge_threshold"], (int, float))
