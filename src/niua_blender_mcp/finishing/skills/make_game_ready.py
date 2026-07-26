"""Skill #1: make an asset game-ready (legacy / light-prop path).

Same accept/revert loop as bake_and_finish (checkpoint -> act -> re-measure
readiness + preservation -> keep iff readiness held AND silhouette is measured
and >= floor, else revert + delete stray helpers), driven through the code-mode
SDK. Fail-closed: unmeasured preservation reverts — never a silent pass.

NOT the default product finisher for dense generator meshes. Raw decimate-to-budget
without bake is the blob path the gatekeeper rejected; evals/finisher.py and the
objective benchmark use bake_and_finish instead. Keep this skill for light props
or explicit agent choice only.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from ...bridge import BridgeError
from .base import Skill

PRESERVATION_FLOOR = 0.85
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


def _preservation_ok(session, subject):
    """Silhouette do-no-harm — fail-closed.

    Unavailable / null / bridge error => not ok (move will revert). Never treat
    unmeasured as a silent pass.
    """
    try:
        pres = session.feedback.preservation(object=subject)
    except BridgeError:
        return False, None
    score = pres.get("preservation")
    if not pres.get("available") or score is None:
        return False, score
    return score >= PRESERVATION_FLOOR, score


def _scene_objects(session):
    return {o["name"] for o in session.scene.info().get("objects", [])}


def _select_all(session, subject):
    session.mesh.select_all(object=subject, action="SELECT")


def _repair(session, subject, info):
    _select_all(session, subject)
    session.mesh.remove_doubles(object=subject)
    session.mesh.recalc_normals(object=subject)


def _decimate_to_budget(session, subject, info):
    q = session.feedback.quality(object=subject, asset_class=info["asset_class"])
    tris = int(q.get("topology", {}).get("tris") or 0)
    budget = int(q.get("asset_class", {}).get("effective_defaults", {}).get("triangle_budget") or 0)
    if tris <= 0 or budget <= 0 or budget >= tris:
        return
    ratio = max(0.01, min(1.0, budget / tris))
    session.modifiers.add(object=subject, type="DECIMATE", name="mcp_decimate")
    session.modifiers.set(object=subject, name="mcp_decimate", property="ratio", value=str(ratio))
    session.modifiers.apply(object=subject, name="mcp_decimate")


def _tris_to_quads(session, subject, info):
    _select_all(session, subject)
    session.mesh.tris_to_quads(object=subject)


def _uv_unwrap(session, subject, info):
    _select_all(session, subject)
    session.uv.smart_unwrap(object=subject)
    session.uv.pack_islands(object=subject)


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
    ("decimate_to_budget", ("engine.within_triangle_budget",), _decimate_to_budget),
    ("tris_to_quads", ("topology.quad_ratio", "topology.ngons"), _tris_to_quads),
    ("uv_unwrap", ("uv.has_uvs", "uv.overlap_detected", "uv.out_of_bounds_loops",
                   "uv.stretch_ratio"), _uv_unwrap),
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
            current = before
            moves_report.append({"move": name, "kept": False, "error": str(exc)[:120]})
            _log(item_id, f"{name}: ERROR {str(exc)[:80]} -> reverted")
            continue
        after = _readiness(session, subject, asset_class)
        r_before = before.get("readiness") or 0.0
        r_after = after.get("readiness") or 0.0
        pres_ok, pres = _preservation_ok(session, subject)
        kept = (r_after >= r_before - _EPS) and pres_ok
        if kept:
            current = after
        else:
            _revert(session, subject, label, objs_before)
            # See bake_and_finish: material edits can outlive mesh revert; keep control state.
            current = before
        moves_report.append({"move": name, "kept": kept,
                             "readiness_before": before.get("readiness"),
                             "readiness_after": after.get("readiness"),
                             "preservation": pres})
        _log(item_id, f"{name}: {_fmt(before.get('readiness'))} -> {_fmt(after.get('readiness'))} "
                      f"pres={_fmt(pres)} {'KEPT' if kept else 'REVERTED'}")

    final = current if current is not None else start
    return {"readiness_start": start.get("readiness"),
            "readiness_final": final.get("readiness"), "moves": moves_report}


SKILL = Skill(
    name="make_game_ready",
    description=("Legacy light-prop finish (no bake): repair, decimate to the triangle "
                 "budget, quads, UV unwrap, PBR maps, LODs, collision, apply transforms — each "
                 "step kept only if readiness holds and silhouette is measured and preserved. "
                 "Prefer bake_and_finish for dense generated meshes (anti-blob default)."),
    asset_classes=("hard_surface_prop", "organic_prop", "generated_cleanup", "from_scratch_prop"),
    run=run,
)
