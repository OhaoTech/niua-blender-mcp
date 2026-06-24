import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


class FakeBpy:
    pass


def test_knowledge_tools_registered():
    names = {spec.name for spec in build_router().specs()}
    reg = build_default_registry()

    for name in ("knowledge.list", "knowledge.load"):
        assert name in names
        command = reg.get(name)
        assert command is not None
        assert command.mutates is False


def test_knowledge_list_and_load():
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    listed = dispatch_on_main(reg, "knowledge.list", {}, ctx)
    assert "uv" in listed["packs"]
    loaded = dispatch_on_main(reg, "knowledge.load", {"name": "uv"}, ctx)
    assert loaded["pack"]["stage"] == "uv"
    assert loaded["pack"]["targets"]["overlap_detected"] is False


def test_knowledge_load_accepts_asset_class_guidance():
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    loaded = dispatch_on_main(
        reg,
        "knowledge.load",
        {"name": "retopo", "asset_class": "generated_cleanup"},
        ctx,
    )

    pack = loaded["pack"]
    assert pack["asset_class"]["id"] == "generated_cleanup"
    assert "generated topology noise" in pack["asset_class"]["guidance"]
    assert pack["recommendations"]["topology.quad_ratio"].startswith("Retopologize")


def test_knowledge_load_unknown_asset_class_fails_cleanly():
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "knowledge.load", {"name": "retopo", "asset_class": "nope"}, ctx)

    assert exc.value.code == INVALID_PARAMS
