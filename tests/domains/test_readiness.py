# tests/domains/test_readiness.py
from __future__ import annotations

from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.domains.policy import finishing_feedback as fb

from domains.fake_bpy import _CUBE_QUADS, _CUBE_VERTS, FakeMesh, FakeObj, env  # noqa: F401

_PASS_TOPO = {"quad_ratio": 1.0, "ngons": 0, "non_manifold_edges": 0}
_PASS_UV = {"has_uvs": True, "out_of_bounds_loops": 0, "overlap_detected": False, "stretch_ratio": 1.0}
_PASS_ORI = {"degenerate_faces": 0, "inward_facing_faces": 0}


def _metrics(engine_all: bool, material_all: bool):
    return {
        "object": "Cube",
        "asset_class": {"id": "hard_surface_prop", "profile_version": 1},
        "topology": dict(_PASS_TOPO),
        "uv": dict(_PASS_UV),
        "orientation": dict(_PASS_ORI),
        "material": {"bake_maps_present": material_all, "data_maps_non_color": material_all,
                     "pbr_maps_present": material_all, "textures_within_size": True,
                     "atlas_ready": material_all},
        "engine": {k: engine_all for k in (
            "within_triangle_budget", "within_material_budget", "within_texture_budget",
            "has_lods", "has_collision_proxy", "lod_triangle_reduction_ok",
            "lod_silhouette_preserved", "has_collision_hulls", "collision_bounds_valid")},
        "scale": {"transform_applied": True},
        "export_profile": {"profile_pass": True},
    }


def test_readiness_reports_both_fractions_and_dedup(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(fb, "quality", lambda ctx, payload: _metrics(engine_all=False, material_all=False))
    out = fb.readiness(ctx, {"object": "Cube", "asset_class": "hard_surface_prop"})
    assert set(out) >= {"object", "readiness", "stage_pass_fraction_mean",
                        "total_gates_deduped", "per_group", "per_gate"}
    assert 0.0 <= out["readiness"] <= 1.0
    # non_manifold_edges==0 appears in retopo AND export_preflight; deduped it is counted once.
    paths = [g["path"] for g in out["per_gate"]]
    assert paths.count("topology.non_manifold_edges") == 1
    # deduped total < raw sum over groups (2+3+4+2+3+9+3 = 26 raw; >=1 duplicate removed).
    raw = sum(s["gates_count"] for s in out["per_group"])
    assert out["total_gates_deduped"] < raw
    # the two fractions are distinct notions and both present
    assert isinstance(out["stage_pass_fraction_mean"], float)


def test_readiness_all_pass_is_one_on_both(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(fb, "quality", lambda ctx, payload: _metrics(engine_all=True, material_all=True))
    out = fb.readiness(ctx, {"object": "Cube", "asset_class": "hard_surface_prop"})
    assert out["readiness"] == 1.0
    assert out["stage_pass_fraction_mean"] == 1.0


def test_readiness_command_registered_readonly() -> None:
    cmd = build_default_registry().get("feedback.readiness")
    assert cmd is not None and cmd.mutates is False and cmd.feedback is None
