from __future__ import annotations

from niua_blender_mcp.kernel import ToolSpec


def test_toolspec_defaults_to_curated_tier() -> None:
    spec = ToolSpec(name="x.y", category="x", summary="s", command="x.y")
    assert spec.tier == "curated"


def test_toolspec_tier_is_settable() -> None:
    spec = ToolSpec(name="x.y", category="x", summary="s", command="x.y", tier="generated")
    assert spec.tier == "generated"
