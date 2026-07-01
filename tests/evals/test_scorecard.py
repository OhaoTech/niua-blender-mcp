from niua_blender_mcp.evals.scorecard import score_item, aggregate

ITEM = {"id": "x", "asset_class": "hard_surface_prop", "senior_threshold": 7.0}


def test_gates_fail_forces_zero():
    card = score_item(ITEM, gates_pass=False, lens_scores={"silhouette": 9.0, "topology": 9.0})
    assert card["overall"] == 0.0
    assert card["senior_pass"] is False


def test_pass_needs_gates_and_threshold():
    card = score_item(ITEM, gates_pass=True, lens_scores={"silhouette": 8.0, "topology": 6.0})
    assert card["overall"] == 7.0
    assert card["senior_pass"] is True


def test_below_threshold_not_senior():
    card = score_item(ITEM, gates_pass=True, lens_scores={"silhouette": 5.0, "topology": 6.0})
    assert card["senior_pass"] is False


def test_aggregate_reports_breakdown_and_weakest_lens():
    cards = [
        score_item(ITEM, True, {"silhouette": 8.0, "topology": 4.0}),
        score_item(ITEM, True, {"silhouette": 9.0, "topology": 5.0}),
    ]
    agg = aggregate(cards)
    assert agg["n_items"] == 2
    assert agg["per_class"]["hard_surface_prop"]["n"] == 2
    assert agg["weakest_lens"] == "topology"
    assert 0.0 <= agg["pass_rate"] <= 1.0
