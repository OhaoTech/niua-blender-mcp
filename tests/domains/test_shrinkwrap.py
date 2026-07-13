"""Offline registration/parity/spec coverage for object.shrinkwrap.

The modifier itself (bpy.ops.object.modifier_apply on a SHRINKWRAP modifier) is
LIVE-validated elsewhere; these tests only cover that the tool is registered on both
sides, its spec fields are correct, and the regenerated SDK exposes it.
"""

from __future__ import annotations


def test_shrinkwrap_registered_both_sides_with_parity():
    from niua_blender_mcp.domains import build_router
    from niua_mcp_bridge.domains import build_default_registry

    server = {s.command for s in build_router().specs()}
    addon = build_default_registry().names()
    assert "object.shrinkwrap" in server
    assert "object.shrinkwrap" in addon


def test_shrinkwrap_spec_is_heavy_mutating_with_expected_params():
    from niua_blender_mcp.domains import build_router

    spec = next(s for s in build_router().specs() if s.name == "object.shrinkwrap")
    assert spec.mutates is True
    assert spec.timeout_tier == "heavy"
    assert {"object", "target", "offset", "apply"} <= set(spec.params)
    assert spec.params["object"].required is True
    assert spec.params["target"].required is True


def test_sdk_exposes_shrinkwrap_after_regen():
    from niua_blender_mcp.client import ToolSession

    session = ToolSession(bridge=None)
    assert hasattr(session.object, "shrinkwrap")
