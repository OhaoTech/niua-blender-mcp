from __future__ import annotations

from niua_blender_mcp.manifest import load_manifest


def test_loads_committed_manifest() -> None:
    m = load_manifest()
    assert m.version
    assert m.operators
    assert "modeling" in m.domains


def test_describe_returns_operator_schema() -> None:
    m = load_manifest()
    info = m.describe("mesh.subdivide")
    assert info is not None
    assert info["id"] == "mesh.subdivide"
    assert "properties" in info


def test_describe_unknown_returns_none() -> None:
    assert load_manifest().describe("nope.nope") is None


def test_search_ranks_exact_match_first() -> None:
    m = load_manifest()
    hits = m.search("subdivide", kind="operator", limit=5)
    assert hits
    assert hits[0]["idname"] == "mesh.subdivide"


def test_search_scopes_to_domain() -> None:
    m = load_manifest()
    hits = m.search("", domain="uv", limit=50)
    assert all(h["idname"].split(".")[0] in m.domains["uv"].categories for h in hits)


def test_manifest_excludes_product_specific_addon_operators() -> None:
    m = load_manifest()
    assert not [idname for idname in m.operators if idname.startswith("niua.")]
