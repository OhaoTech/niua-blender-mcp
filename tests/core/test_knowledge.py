import pytest

from niua_mcp_bridge.core.knowledge import list_packs, load_pack, stage_pack


def test_lists_stage_knowledge_packs():
    assert list_packs() == ["export_preflight", "optimize", "repair", "retopo", "uv"]


def test_uv_pack_contains_cited_standards_and_targets():
    pack = stage_pack("uv")

    assert pack["stage"] == "uv"
    assert "texel density" in pack["standards"].lower()
    assert pack["targets"]["overlap_detected"] is False
    assert pack["targets"]["stretch_ratio_max"] == 2.0
    assert pack["sources"]


def test_unknown_pack_is_key_error():
    with pytest.raises(KeyError, match="unknown knowledge pack"):
        load_pack("ghost")
