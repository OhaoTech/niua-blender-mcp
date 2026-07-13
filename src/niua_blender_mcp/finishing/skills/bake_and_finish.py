"""Skill #2: bake-transfer finish. Like make_game_ready, but the detail lost to
budget reduction is recovered by baking the pre-reduction high-poly onto the
low-poly before it's discarded, and the do-no-harm gate reads BOTH silhouette
(preservation) AND surface fidelity (SSIM) from a single feedback.preservation
call — a step is only kept if readiness held and *both* measured axes stayed
above their floors (an axis the bridge doesn't report never blocks; that's
measure-and-flag, not silent pass).

Two reducers, gated identically, in this fixed order: bake_retopo (voxel-remesh
-> decimate collapse to budget) then bake_decimate (DECIMATE modifier straight
on the high-poly). Neither reducer wins universally -- retopo helps
bulky/hard-surface meshes but its voxel step can merge thin features (fingers,
blades) on organic figures, where a straight decimate holds fidelity better.
Both reducers shrinkwrap the reduced mesh back onto the pre-reduction
high-poly surface before the bake, removing the offset/blocky lumps-and-holes
a voxel remesh leaves behind. Rather than pick a reducer heuristically, the
accept/revert loop *is* the router:

  - bake_retopo fires first (its gate, engine.within_triangle_budget, is
    failing on the raw high-poly). If retopo+bake is KEPT (fidelity held) the
    budget is now met, so bake_decimate's gate is no longer failing and it
    SKIPS.
  - If bake_retopo is REVERTED (fidelity dropped), the object is back to
    high-poly, so the budget gate still fails and bake_decimate FIRES,
    decimating + baking instead. The loop keeps it if fidelity holds there.

So each asset ends up with whichever reducer preserved fidelity, decided by
the same surface_fidelity ruler that gates every other move -- no new metric,
no per-asset-class heuristic.

Same accept/revert loop and report shape as make_game_ready.py; see that
module's docstring for the general loop rationale. This file intentionally
mirrors its structure so the two skills stay easy to diff.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from ...bridge import BridgeError
from .base import Skill

# Server-side copies of blender_addon/niua_mcp_bridge/finishing/preservation_ledger.py's
# floor values. That module is addon-only (imports live inside niua_mcp_bridge, which is
# not importable from the server process), so the values are duplicated here exactly like
# make_game_ready.py hardcodes its own PRESERVATION_FLOOR = 0.85.
PRESERVATION_FLOOR = 0.85
# Fallback-only: the addon's preservation_ledger.SURFACE_FIDELITY_FLOOR is the live,
# authoritative floor -- it's baked into surface_fidelity["surface_fidelity_pass"] by
# feedback.preservation. This constant only matters for an old addon build whose
# preservation() response predates that key (see _harm_ok below).
SURFACE_FIDELITY_FLOOR = 0.60  # evidence-calibrated; see finishing/preservation_ledger.py + surface-fidelity-validation.md
_EPS = 1e-9


def _fmt(x: Any) -> str:
    return f"{x:.3f}" if isinstance(x, (int, float)) else "?"


def _log(item_id: str, msg: str) -> None:
    print(f"    [skill:{item_id}] {msg}", file=sys.stderr)


def _readiness(session, subject, asset_class):
    return session.feedback.readiness(object=subject, asset_class=asset_class)


def _failing(readiness, *paths):
    by_path = {g["path"]: g for g in (readiness or {}).get("per_gate", [])}
    return any(p in by_path and not by_path[p]["pass"] for p in paths)


def _harm_ok(session, subject):
    """Both do-no-harm axes from one preservation call.

    Unmeasured axis never blocks (measure-and-flag): if the bridge can't report
    silhouette or fidelity, that axis passes by default and only the axes that
    were actually measured gate the keep decision.

    Fidelity gating defers to the addon's own authoritative floor
    (preservation_ledger.SURFACE_FIDELITY_FLOOR, live-mirrored into
    surface_fidelity["surface_fidelity_pass"] by feedback.preservation) when that key
    is present; SURFACE_FIDELITY_FLOOR here is only a fallback for an old addon build
    whose response predates that key.
    """
    try:
        pres = session.feedback.preservation(object=subject)
    except BridgeError:
        return True, None, None
    sil = pres.get("preservation")
    sf = pres.get("surface_fidelity") or {}
    fid = sf.get("fidelity") if sf.get("available") else None
    sil_ok = (not pres.get("available")) or sil is None or sil >= PRESERVATION_FLOOR
    if "surface_fidelity_pass" in sf:
        fid_ok = fid is None or bool(sf.get("surface_fidelity_pass"))
    else:
        fid_ok = fid is None or fid >= SURFACE_FIDELITY_FLOOR
    return (sil_ok and fid_ok), sil, fid


def _scene_objects(session):
    return {o["name"] for o in session.scene.info().get("objects", [])}


def _select_all(session, subject):
    session.mesh.select_all(object=subject, action="SELECT")


def _repair(session, subject, info):
    _select_all(session, subject)
    session.mesh.remove_doubles(object=subject)
    session.mesh.recalc_normals(object=subject)


def _budget_and_tris(session, subject, info):
    q = session.feedback.quality(object=subject, asset_class=info["asset_class"])
    budget = int(q.get("asset_class", {}).get("effective_defaults", {}).get("triangle_budget") or 0)
    tris = int(q.get("topology", {}).get("tris") or 0)
    return budget, tris


def _reduce_retopo(session, subject, budget, tris):
    """Voxel-remesh -> decimate collapse to the budget. Clean, manifold low-poly,
    but the voxel step can merge thin/adjacent features (fingers, blades) on
    organic meshes -- that's caught downstream by the surface-fidelity gate, not
    here."""
    if budget > 0 and (tris <= 0 or budget < tris):
        target_faces = max(1, budget // 2)  # budget is in tris; retopo targets FACES
        session.object.retopo(object=subject, target_faces=target_faces)


def _reduce_decimate(session, subject, budget, tris):
    """DECIMATE modifier to the budget ratio -- the pre-retopo path, recovered
    as the fallback reducer for meshes where retopo's voxel step hurts fidelity."""
    if tris > 0 and budget > 0 and budget < tris:
        ratio = max(0.01, min(1.0, budget / tris))
        session.modifiers.add(object=subject, type="DECIMATE", name="niua_decimate")
        session.modifiers.set(object=subject, name="niua_decimate", property="ratio", value=str(ratio))
        session.modifiers.apply(object=subject, name="niua_decimate")


def _bake_with(session, subject, info, reduce_fn):
    """Shared bake plumbing for both reducers: duplicate the high-poly, run
    reduce_fn to hit the triangle budget, shrinkwrap the reduced mesh back onto
    the high-poly surface (removes voxel-remesh offset/lumps-and-holes before
    the bake has to carry them), unwrap, bake normal+AO from the high-poly,
    then discard the high-poly source."""
    high = f"{subject}__high"
    session.object.duplicate(object=subject, name=high)  # keep the pre-reduction detail as bake source
    budget, tris = _budget_and_tris(session, subject, info)
    reduce_fn(session, subject, budget, tris)
    session.object.shrinkwrap(object=subject, target=high)  # snap onto the high-poly surface
    session.mesh.select_all(object=subject, action="SELECT")
    session.uv.smart_unwrap(object=subject)
    session.uv.pack_islands(object=subject)
    session.object.bake_transfer(source=high, target=subject, maps="NORMAL,AO")
    session.object.delete(objects=high)  # remove the high-poly source; low-poly carries baked detail


def _bake_retopo(session, subject, info):
    _bake_with(session, subject, info, _reduce_retopo)


def _bake_decimate(session, subject, info):
    _bake_with(session, subject, info, _reduce_decimate)


def _tris_to_quads(session, subject, info):
    _select_all(session, subject)
    session.mesh.tris_to_quads(object=subject)


def _pbr_maps(session, subject, info):
    session.shading.prepare_pbr_maps(object=subject)


def _lod(session, subject, info):
    session.object.lod_create(object=subject, ratio=0.5, apply=True)


def _collision(session, subject, info):
    session.object.collision_proxy_create(object=subject)
    session.object.collision_hulls_create(object=subject)


def _apply_transform(session, subject, info):
    session.object.transform_apply(object=subject)


MOVES: list[tuple[str, tuple[str, ...], Callable[[Any, str, dict], None]]] = [
    ("repair", ("orientation.degenerate_faces", "orientation.inward_facing_faces",
                "topology.non_manifold_edges"), _repair),
    # Both reducers share the same gate: bake_retopo tries first, and if it's kept the
    # budget gate stops failing so bake_decimate is a no-op skip; if bake_retopo is
    # reverted (fidelity dropped) the gate is still failing and bake_decimate fires as
    # the fallback reducer. See module docstring for the full routing rationale.
    ("bake_retopo", ("engine.within_triangle_budget",), _bake_retopo),
    ("bake_decimate", ("engine.within_triangle_budget",), _bake_decimate),
    ("tris_to_quads", ("topology.quad_ratio", "topology.ngons"), _tris_to_quads),
    ("pbr_maps", ("material.pbr_maps_present", "material.bake_maps_present",
                  "material.data_maps_non_color", "material.textures_within_size",
                  "material.atlas_ready"), _pbr_maps),
    ("lod", ("engine.has_lods", "engine.lod_triangle_reduction_ok",
             "engine.lod_silhouette_preserved"), _lod),
    ("collision", ("engine.has_collision_proxy", "engine.has_collision_hulls",
                   "engine.collision_bounds_valid"), _collision),
    ("apply_transform", ("scale.transform_applied",), _apply_transform),
]

TOOLS_USED = {
    "feedback.readiness", "feedback.preservation", "feedback.quality",
    "session.checkpoint", "session.revert", "scene.info", "object.delete",
    "mesh.select_all", "mesh.remove_doubles", "mesh.recalc_normals", "mesh.tris_to_quads",
    "modifiers.add", "modifiers.set", "modifiers.apply",
    "uv.smart_unwrap", "uv.pack_islands",
    "shading.prepare_pbr_maps",
    "object.lod_create", "object.collision_proxy_create", "object.collision_hulls_create",
    "object.transform_apply",
    "object.duplicate", "object.bake_transfer", "object.retopo", "object.shrinkwrap",
}


def _revert(session, subject, label, objs_before):
    strays = sorted(_scene_objects(session) - objs_before)
    if strays:
        session.object.delete(objects=",".join(strays))
    session.session.revert(object=subject, label=label)


def run(session, subject: str, params: dict) -> dict:
    asset_class = params.get("asset_class")
    item_id = str(params.get("id", subject))
    info = {"asset_class": asset_class}
    moves_report: list[dict] = []
    start = _readiness(session, subject, asset_class)
    current = start

    for name, paths, apply_move in MOVES:
        before = current if current is not None else _readiness(session, subject, asset_class)
        current = before
        if not _failing(before, *paths):
            continue
        label = f"finisher:{name}"
        session.session.checkpoint(object=subject, label=label)
        objs_before = _scene_objects(session)
        current = None
        try:
            apply_move(session, subject, info)
        except BridgeError as exc:
            _revert(session, subject, label, objs_before)
            moves_report.append({"move": name, "kept": False, "error": str(exc)[:120]})
            _log(item_id, f"{name}: ERROR {str(exc)[:80]} -> reverted")
            continue
        after = _readiness(session, subject, asset_class)
        r_before = before.get("readiness") or 0.0
        r_after = after.get("readiness") or 0.0
        harm_ok, sil, fid = _harm_ok(session, subject)
        kept = (r_after >= r_before - _EPS) and harm_ok
        if kept:
            current = after
        else:
            _revert(session, subject, label, objs_before)
        moves_report.append({"move": name, "kept": kept,
                             "readiness_before": before.get("readiness"),
                             "readiness_after": after.get("readiness"),
                             "preservation": sil, "surface_fidelity": fid})
        _log(item_id, f"{name}: {_fmt(before.get('readiness'))} -> {_fmt(after.get('readiness'))} "
                      f"pres={_fmt(sil)} fid={_fmt(fid)} {'KEPT' if kept else 'REVERTED'}")

    final = _readiness(session, subject, asset_class)
    return {"readiness_start": start.get("readiness"),
            "readiness_final": final.get("readiness"), "moves": moves_report}


SKILL = Skill(
    name="bake_and_finish",
    description=("Take a raw generated mesh to game-ready with bake-transfer detail recovery: "
                 "repair, duplicate the high-poly as a bake source, reduce to the triangle "
                 "budget via retopo (voxel-remesh -> decimate collapse) or, if that hurts "
                 "fidelity, decimate instead, shrinkwrap the reduced mesh back onto the "
                 "high-poly surface, unwrap, bake normal+AO maps from the high-poly, quads, "
                 "PBR maps, LODs, collision, apply transforms — each step kept only if "
                 "readiness holds and both silhouette AND surface fidelity are preserved."),
    asset_classes=("hard_surface_prop", "organic_prop", "generated_cleanup", "from_scratch_prop"),
    run=run,
)
