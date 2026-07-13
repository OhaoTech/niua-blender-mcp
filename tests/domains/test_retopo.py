"""Offline registration/parity/spec coverage for object.retopo.

The remesh itself (bpy.ops.object.voxel_remesh / quadriflow_remesh) is LIVE-validated
elsewhere; these tests only cover that the tool is registered on both sides, its spec
fields are correct, and the regenerated SDK exposes it.
"""

from __future__ import annotations


def test_retopo_registered_both_sides_with_parity():
    from niua_blender_mcp.domains import build_router
    from niua_mcp_bridge.domains import build_default_registry

    server = {s.command for s in build_router().specs()}
    addon = build_default_registry().names()
    assert "object.retopo" in server
    assert "object.retopo" in addon


def test_retopo_spec_is_heavy_mutating_with_expected_params():
    from niua_blender_mcp.domains import build_router

    spec = next(s for s in build_router().specs() if s.name == "object.retopo")
    assert spec.mutates is True
    assert spec.timeout_tier == "heavy"
    assert {"object", "target_faces"} <= set(spec.params)


def test_sdk_exposes_retopo_after_regen():
    from niua_blender_mcp.client import ToolSession

    session = ToolSession(bridge=None)
    assert hasattr(session.object, "retopo")
