from __future__ import annotations

from niua_blender_mcp.evals.objective_bench import aggregate_objective, score_item_objective

ITEM = {"id": "barrel", "asset_class": "from_scratch_prop"}


def test_harm_flagged_below_floor() -> None:
    card = score_item_objective(ITEM, readiness=1.0, stage_pass_fraction=1.0,
                                preservation=0.80, preservation_available=True)
    assert card["preservation_measured"] is True
    assert card["preservation_pass"] is False
    assert card["harm_flagged"] is True


def test_floor_boundary_passes_at_085() -> None:
    card = score_item_objective(ITEM, readiness=0.9, stage_pass_fraction=0.9,
                                preservation=0.85, preservation_available=True)
    assert card["preservation_pass"] is True
    assert card["harm_flagged"] is False


def test_unmeasured_is_not_failed() -> None:
    card = score_item_objective(ITEM, readiness=0.5, stage_pass_fraction=0.4,
                                preservation=None, preservation_available=False)
    assert card["preservation_measured"] is False
    assert card["harm_flagged"] is False       # unmeasured != harm
    assert card["preservation_pass"] is False


def test_aggregate_excludes_unmeasured_from_preservation_mean() -> None:
    cards = [
        score_item_objective({"id": "a", "asset_class": "hard_surface_prop"},
                             readiness=1.0, stage_pass_fraction=1.0, preservation=0.95, preservation_available=True),
        score_item_objective({"id": "b", "asset_class": "hard_surface_prop"},
                             readiness=0.5, stage_pass_fraction=0.4, preservation=None, preservation_available=False),
    ]
    agg = aggregate_objective(cards)
    assert agg["n_items"] == 2
    assert agg["n_measured"] == 1
    assert agg["n_unmeasured"] == 1
    assert abs(agg["mean_readiness"] - 0.75) < 1e-9       # readiness always measurable
    assert abs(agg["mean_preservation"] - 0.95) < 1e-9    # only the measured item
    assert agg["valid"] is False                          # a headless item present


def test_aggregate_empty_and_all_unmeasured() -> None:
    assert aggregate_objective([])["mean_preservation"] is None
    card = score_item_objective({"id": "c", "asset_class": "organic_prop"},
                                readiness=0.0, stage_pass_fraction=0.0, preservation=None, preservation_available=False)
    agg = aggregate_objective([card])
    assert agg["mean_preservation"] is None
    assert agg["valid"] is False


def test_readiness_unmeasured_is_not_coerced_to_zero_failure() -> None:
    # A None readiness (e.g. no applicable gates) must not silently read as "0% ready".
    card = score_item_objective(ITEM, readiness=None, stage_pass_fraction=None,
                                preservation=0.95, preservation_available=True)
    assert card["readiness_measured"] is False
    assert card["stage_pass_fraction"] is None
    assert card["fully_ready"] is False    # honestly unknown, not a failed 0.0


def test_aggregate_excludes_readiness_unmeasured_from_readiness_mean() -> None:
    cards = [
        score_item_objective({"id": "a", "asset_class": "hard_surface_prop"},
                             readiness=1.0, stage_pass_fraction=1.0, preservation=0.95, preservation_available=True),
        score_item_objective({"id": "b", "asset_class": "hard_surface_prop"},
                             readiness=None, stage_pass_fraction=None, preservation=0.90, preservation_available=True),
    ]
    agg = aggregate_objective(cards)
    assert agg["n_readiness_measured"] == 1
    assert agg["n_readiness_unmeasured"] == 1
    # b's missing readiness must not drag the mean toward 0 -- it is excluded, not coerced.
    assert abs(agg["mean_readiness"] - 1.0) < 1e-9


def test_godot_axis_measured_ok():
    card = score_item_objective(
        {"id": "x", "asset_class": "organic_prop"},
        readiness=0.5, stage_pass_fraction=0.5,
        preservation=1.0, preservation_available=True,
        godot_import={"available": True, "ok": True},
    )
    assert card["godot_import_measured"] is True and card["godot_import_ok"] is True


def test_godot_axis_unmeasured_is_none_not_false():
    for gi in (None, {"available": False, "reason": "no binary"}):
        card = score_item_objective(
            {"id": "x", "asset_class": "organic_prop"},
            readiness=0.5, stage_pass_fraction=0.5,
            preservation=1.0, preservation_available=True, godot_import=gi,
        )
        assert card["godot_import_measured"] is False
        assert card["godot_import_ok"] is None


def test_low_surface_fidelity_flags_harm():
    card = score_item_objective(
        {"id": "x", "asset_class": "hard_surface_prop"},
        readiness=0.6, stage_pass_fraction=0.6,
        preservation=1.0, preservation_available=True,
        surface_fidelity=0.5, surface_fidelity_available=True)
    assert card["surface_fidelity_measured"] is True
    assert card["harm_flagged"] is True  # fidelity below floor = harm even if silhouette passed


def test_unmeasured_fidelity_is_none_not_zero():
    card = score_item_objective(
        {"id": "x", "asset_class": "hard_surface_prop"},
        readiness=0.6, stage_pass_fraction=0.6,
        preservation=1.0, preservation_available=True,
        surface_fidelity=None, surface_fidelity_available=False)
    assert card["surface_fidelity_measured"] is False
    assert card["surface_fidelity"] is None
    assert card["harm_flagged"] is False


def test_surface_fidelity_pass_does_not_flag_harm():
    card = score_item_objective(
        {"id": "x", "asset_class": "hard_surface_prop"},
        readiness=0.6, stage_pass_fraction=0.6,
        preservation=1.0, preservation_available=True,
        surface_fidelity=0.95, surface_fidelity_available=True)
    assert card["surface_fidelity_measured"] is True
    assert card["surface_fidelity"] == 0.95
    assert card["harm_flagged"] is False


def test_preservation_harm_still_fires_without_fidelity_axis():
    # Existing preservation-below-floor harm behavior must be untouched by the new axis.
    card = score_item_objective(
        ITEM, readiness=1.0, stage_pass_fraction=1.0,
        preservation=0.80, preservation_available=True)
    assert card["surface_fidelity_measured"] is False
    assert card["harm_flagged"] is True


def test_aggregate_excludes_unmeasured_from_fidelity_mean():
    cards = [
        score_item_objective({"id": "a", "asset_class": "hard_surface_prop"},
                             readiness=1.0, stage_pass_fraction=1.0, preservation=0.95, preservation_available=True,
                             surface_fidelity=0.92, surface_fidelity_available=True),
        score_item_objective({"id": "b", "asset_class": "hard_surface_prop"},
                             readiness=0.5, stage_pass_fraction=0.4, preservation=0.95, preservation_available=True,
                             surface_fidelity=None, surface_fidelity_available=False),
    ]
    agg = aggregate_objective(cards)
    assert agg["n_fidelity_measured"] == 1
    assert abs(agg["mean_surface_fidelity"] - 0.92) < 1e-9


def test_aggregate_mean_surface_fidelity_none_when_unmeasured():
    assert aggregate_objective([])["mean_surface_fidelity"] is None
    card = score_item_objective({"id": "c", "asset_class": "organic_prop"},
                                readiness=0.0, stage_pass_fraction=0.0, preservation=None, preservation_available=False,
                                surface_fidelity=None, surface_fidelity_available=False)
    agg = aggregate_objective([card])
    assert agg["mean_surface_fidelity"] is None
    assert agg["n_fidelity_measured"] == 0


def test_aggregate_counts_godot_axis():
    ok = {"godot_import_measured": True, "godot_import_ok": True}
    bad = {"godot_import_measured": True, "godot_import_ok": False}
    unm = {"godot_import_measured": False, "godot_import_ok": None}
    base = {"asset_class": "a", "readiness_measured": True, "readiness": 1.0,
            "stage_pass_fraction": 1.0, "preservation_measured": True,
            "preservation": 1.0, "preservation_pass": True,
            "harm_flagged": False, "fully_ready": True}
    agg = aggregate_objective([{**base, **ok}, {**base, **bad}, {**base, **unm}])
    assert agg["n_godot_measured"] == 2
    assert agg["n_godot_import_ok"] == 1
