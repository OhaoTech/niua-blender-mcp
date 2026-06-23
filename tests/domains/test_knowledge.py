from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


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
