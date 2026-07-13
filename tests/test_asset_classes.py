from __future__ import annotations

import pytest

from niua_blender_mcp.finishing import asset_classes as server_asset_classes
from niua_mcp_bridge.finishing import asset_classes as addon_asset_classes


def test_server_and_addon_asset_class_registries_match() -> None:
    server = {profile["id"]: profile for profile in server_asset_classes.list_asset_classes()}
    addon = {profile["id"]: profile for profile in addon_asset_classes.list_asset_classes()}

    assert sorted(server) == [
        "character",
        "from_scratch_prop",
        "generated_cleanup",
        "hard_surface_prop",
        "organic_prop",
    ]
    assert server == addon


def test_asset_class_defaults_are_returned_as_copies() -> None:
    first = addon_asset_classes.get_asset_class("hard_surface_prop")
    first["defaults"]["triangle_budget"] = 1

    second = addon_asset_classes.get_asset_class("hard_surface_prop")

    assert second["defaults"]["triangle_budget"] == 5000


def test_apply_asset_class_defaults_preserves_explicit_parameters() -> None:
    payload, meta = addon_asset_classes.apply_asset_class_defaults(
        {"asset_class": "organic_prop", "triangle_budget": 1234}
    )

    assert payload["triangle_budget"] == 1234
    assert payload["material_budget"] == 3
    assert meta["id"] == "organic_prop"
    assert meta["profile_version"] == 1
    assert meta["asset_class_defaulted"] is False
    assert meta["effective_defaults"]["triangle_budget"] == 1234


def test_missing_asset_class_defaults_to_hard_surface_prop() -> None:
    payload, meta = addon_asset_classes.apply_asset_class_defaults({})

    assert payload["triangle_budget"] == 5000
    assert meta["id"] == "hard_surface_prop"
    assert meta["asset_class_defaulted"] is True


def test_unknown_asset_class_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown asset class: nope"):
        addon_asset_classes.get_asset_class("nope")


def test_registry_modules_do_not_expose_unused_default_key_marker() -> None:
    assert not hasattr(addon_asset_classes, "_DEFAULT_KEYS")
    assert not hasattr(server_asset_classes, "_DEFAULT_KEYS")


@pytest.mark.parametrize("module", [server_asset_classes, addon_asset_classes])
def test_profiles_are_numbers_only_no_prose(module) -> None:
    for profile in module.list_asset_classes():
        assert "stage_targets" not in profile, profile["id"]
        assert "guidance" not in profile, profile["id"]
        assert set(profile) == {"id", "profile_version", "label", "summary",
                                "defaults", "gate_overrides"}


@pytest.mark.parametrize("module", [server_asset_classes, addon_asset_classes])
def test_apply_defaults_takes_no_pipeline_state(module) -> None:
    import inspect
    sig = inspect.signature(module.apply_asset_class_defaults)
    assert list(sig.parameters) == ["payload"]


def test_gate_overrides_replace_existing_paths_only() -> None:
    base = [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.95},
        {"path": "topology.ngons", "op": "==", "value": 0},
    ]
    profile = addon_asset_classes.get_asset_class("generated_cleanup")

    gates, applied = addon_asset_classes.apply_gate_overrides(base, profile, "retopo")

    assert gates == [
        {"path": "topology.quad_ratio", "op": ">=", "value": 0.98},
        {"path": "topology.ngons", "op": "==", "value": 0},
    ]
    assert applied == {"retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.98}}}


def test_invalid_gate_override_path_raises_value_error() -> None:
    base = [{"path": "topology.quad_ratio", "op": ">=", "value": 0.95}]
    profile = {
        "id": "bad",
        "profile_version": 1,
        "label": "Bad",
        "summary": "Bad profile",
        "defaults": {},
        "gate_overrides": {"retopo": {"topology.missing": {"op": ">=", "value": 1}}},
    }

    with pytest.raises(ValueError, match="invalid gate override path for retopo: topology.missing"):
        addon_asset_classes.apply_gate_overrides(base, profile, "retopo")
