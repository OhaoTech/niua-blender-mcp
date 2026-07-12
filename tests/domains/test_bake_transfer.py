"""Offline registration/parity/spec coverage for object.bake_transfer.

The bake itself (bpy.ops.object.bake) is LIVE-validated elsewhere; these tests only
cover that the tool is registered on both sides, its spec fields are correct, and the
regenerated SDK exposes it.
"""

from __future__ import annotations


def test_bake_transfer_registered_both_sides_with_parity():
    from niua_blender_mcp.domains import build_router
    from niua_mcp_bridge.domains import build_default_registry

    server = {s.command for s in build_router().specs()}
    addon = build_default_registry().names()
    assert "object.bake_transfer" in server
    assert "object.bake_transfer" in addon


def test_bake_transfer_spec_is_heavy_and_mutating():
    from niua_blender_mcp.domains import build_router

    spec = next(s for s in build_router().specs() if s.name == "object.bake_transfer")
    assert spec.mutates is True
    assert spec.timeout_tier == "heavy"
    assert {"source", "target"} <= set(spec.params)


def test_sdk_exposes_bake_transfer_after_regen():
    from niua_blender_mcp.client import ToolSession

    session = ToolSession(bridge=None)
    assert hasattr(session.object, "bake_transfer")
