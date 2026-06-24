from __future__ import annotations

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


class FakeBpy:
    pass


def test_asset_class_tools_registered() -> None:
    names = {spec.name for spec in build_router().specs()}
    reg = build_default_registry()

    for name in ("asset_class.list", "asset_class.describe"):
        assert name in names
        command = reg.get(name)
        assert command is not None
        assert command.mutates is False


def test_asset_class_list_returns_summaries() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    out = dispatch_on_main(reg, "asset_class.list", {}, ctx)

    assert [item["id"] for item in out["asset_classes"]] == [
        "from_scratch_prop",
        "generated_cleanup",
        "hard_surface_prop",
        "organic_prop",
    ]
    assert {"id", "label", "summary", "profile_version"} <= set(out["asset_classes"][0])
    assert "defaults" not in out["asset_classes"][0]


def test_asset_class_describe_returns_complete_profile() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    out = dispatch_on_main(reg, "asset_class.describe", {"asset_class": "generated_cleanup"}, ctx)

    profile = out["asset_class"]
    assert profile["id"] == "generated_cleanup"
    assert profile["profile_version"] == 1
    assert profile["defaults"]["triangle_budget"] == 6000
    assert profile["gate_overrides"]["retopo"]["topology.quad_ratio"]["value"] == 0.98
    assert "retopo" in profile["guidance"]


def test_asset_class_describe_unknown_class_fails_cleanly() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "asset_class.describe", {"asset_class": "nope"}, ctx)

    assert exc.value.code == INVALID_PARAMS
    assert "unknown asset class: nope" in str(exc.value)
