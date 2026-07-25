"""Offline registration/parity/spec coverage for object.retopo.

The remesh itself (bpy.ops.object.voxel_remesh, then a decimate collapse to the face
budget -- quadriflow_remesh was dropped: it silently cancels at aggressive targets and
segfaults Blender on dense multi-part meshes) is LIVE-validated elsewhere; these tests
cover that the tool is registered on both sides, its spec fields are correct, the
regenerated SDK exposes it, and the voxel-resolution safety cap's pure math.
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


def test_voxel_cap_leaves_small_bbox_untouched():
    from niua_mcp_bridge.domains.objects import _capped_voxel_size

    # 1x1x1 bbox / (0.05**3 voxel_size) ~= 8000 voxels -- far under the 5M cap.
    assert _capped_voxel_size([1.0, 1.0, 1.0], 0.05) == 0.05


def test_voxel_cap_raises_voxel_size_for_a_huge_bbox():
    from niua_mcp_bridge.domains.objects import _VOXEL_COUNT_CAP, _capped_voxel_size

    dims = [100.0, 100.0, 100.0]
    requested = 0.05  # bbox_volume / requested**3 = 1e6 / 1.25e-4 = 8e9, way over the cap
    capped = _capped_voxel_size(dims, requested)
    assert capped > requested
    bbox_volume = dims[0] * dims[1] * dims[2]
    assert bbox_volume / (capped**3) <= _VOXEL_COUNT_CAP + 1e-6


def test_voxel_cap_never_shrinks_the_requested_size():
    from niua_mcp_bridge.domains.objects import _capped_voxel_size

    # A large voxel_size already keeps the count under the cap -- the cap must not
    # refine (lower) it, only ever coarsen an under-sized request.
    assert _capped_voxel_size([100.0, 100.0, 100.0], 5.0) == 5.0


def test_voxel_unsafe_when_multiple_loose_parts():
    from niua_mcp_bridge.domains.objects import _voxel_unsafe, _VOXEL_UNSAFE_PARTS

    class _Mesh:
        pass

    class _FakeRisk:
        @staticmethod
        def risk(_mesh):
            return {"parts": _VOXEL_UNSAFE_PARTS, "non_manifold_edges": 0}

    import niua_mcp_bridge.domains.objects as objects_mod
    original = objects_mod._mesh_topology_risk
    objects_mod._mesh_topology_risk = lambda mesh: {"parts": 3, "non_manifold_edges": 10}
    try:
        unsafe, reason = _voxel_unsafe(_Mesh())
        assert unsafe is True
        assert "loose_parts" in reason
    finally:
        objects_mod._mesh_topology_risk = original


def test_voxel_unsafe_when_high_non_manifold():
    from niua_mcp_bridge.domains.objects import _voxel_unsafe, _VOXEL_UNSAFE_NON_MANIFOLD
    import niua_mcp_bridge.domains.objects as objects_mod

    original = objects_mod._mesh_topology_risk
    objects_mod._mesh_topology_risk = lambda mesh: {
        "parts": 1, "non_manifold_edges": _VOXEL_UNSAFE_NON_MANIFOLD,
    }
    try:
        unsafe, reason = _voxel_unsafe(object())
        assert unsafe is True
        assert "non_manifold" in reason
    finally:
        objects_mod._mesh_topology_risk = original


def test_voxel_safe_on_clean_single_part():
    import niua_mcp_bridge.domains.objects as objects_mod

    original = objects_mod._mesh_topology_risk
    objects_mod._mesh_topology_risk = lambda mesh: {"parts": 1, "non_manifold_edges": 0}
    try:
        unsafe, reason = objects_mod._voxel_unsafe(object())
        assert unsafe is False
        assert reason == ""
    finally:
        objects_mod._mesh_topology_risk = original


def test_retopo_spec_includes_mode():
    from niua_blender_mcp.domains import build_router

    spec = next(s for s in build_router().specs() if s.name == "object.retopo")
    assert "mode" in spec.params
