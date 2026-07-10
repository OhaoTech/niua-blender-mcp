"""Deterministic gate-driven finisher: the benchmark's reference finishing agent.

Wired into scripts/run_objective_benchmark.py via
  --mode agent --finisher niua_blender_mcp.evals.finisher:finish

Reads the order-free readiness gates and, for each failing gate group, applies the
smallest standard fix — every fix wrapped in the per-edit accept/revert loop:
session.checkpoint -> act -> re-measure readiness + preservation -> keep iff readiness
did not drop AND preservation (when measured) stays above the floor, else session.revert.
Moves that create helper objects (LODs, collision) get those objects deleted on revert.
No LLM decides anything here, so benchmark deltas measure the TOOL surface, not the
model driving it. Do-no-harm follows measure-and-flag: an UNMEASURED preservation never
blocks a move (a headless run must not deadlock the finisher), a measured drop below
the floor always reverts it.

Readiness reads are cached across SKIPPED moves only (nothing changed, so the last
snapshot is still true); after any move that FIRED — kept or reverted — the next
gate check re-reads fresh. Honest state tracking at one extra read per fired move,
still far cheaper than a per-move re-read across the 8-move loop.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from ..bridge import BridgeError

PRESERVATION_FLOOR = 0.85
_EPS = 1e-9


def _fmt(x: Any) -> str:
    return f"{x:.3f}" if isinstance(x, (int, float)) else "?"


def _log(item_id: str, msg: str) -> None:
    print(f"    [finisher:{item_id}] {msg}", file=sys.stderr)


def _payload(subject: str, asset_class: str | None) -> dict:
    return {"object": subject, "asset_class": asset_class} if asset_class else {"object": subject}


def _readiness(bridge: Any, subject: str, asset_class: str | None) -> dict:
    return bridge.call("feedback.readiness", _payload(subject, asset_class))


def _failing(readiness: dict, *paths: str) -> bool:
    by_path = {g["path"]: g for g in (readiness or {}).get("per_gate", [])}
    return any(p in by_path and not by_path[p]["pass"] for p in paths)


def _preservation_ok(bridge: Any, subject: str) -> tuple[bool, float | None]:
    """Measured-and-below-floor is the only failure; unmeasured is not harm."""
    try:
        pres = bridge.call("feedback.preservation", {"object": subject})
    except BridgeError:
        return True, None
    score = pres.get("preservation")
    if not pres.get("available") or score is None:
        return True, None
    return score >= PRESERVATION_FLOOR, score


def _scene_objects(bridge: Any) -> set[str]:
    return {o["name"] for o in bridge.call("scene.info", {}).get("objects", [])}


# ---- the moves (senior finishing order; each fires only on its failing gates) --------

def _select_all(bridge: Any, subject: str) -> None:
    bridge.call("mesh.select_all", {"object": subject, "action": "SELECT"})


def _repair(bridge: Any, subject: str, info: dict) -> None:
    _select_all(bridge, subject)
    bridge.call("mesh.remove_doubles", {"object": subject})
    bridge.call("mesh.recalc_normals", {"object": subject})


def _decimate_to_budget(bridge: Any, subject: str, info: dict) -> None:
    q = bridge.call("feedback.quality", _payload(subject, info["asset_class"]))
    tris = int(q.get("topology", {}).get("tris") or 0)
    budget = int(q.get("asset_class", {}).get("effective_defaults", {}).get("triangle_budget") or 0)
    if tris <= 0 or budget <= 0 or budget >= tris:
        return
    ratio = max(0.01, min(1.0, budget / tris))
    bridge.call("modifiers.add", {"object": subject, "type": "DECIMATE", "name": "niua_decimate"})
    bridge.call("modifiers.set", {"object": subject, "name": "niua_decimate",
                                  "property": "ratio", "value": str(ratio)})
    bridge.call("modifiers.apply", {"object": subject, "name": "niua_decimate"})


def _tris_to_quads(bridge: Any, subject: str, info: dict) -> None:
    _select_all(bridge, subject)
    bridge.call("mesh.tris_to_quads", {"object": subject})


def _uv_unwrap(bridge: Any, subject: str, info: dict) -> None:
    _select_all(bridge, subject)
    bridge.call("uv.smart_unwrap", {"object": subject})
    bridge.call("uv.pack_islands", {"object": subject})


def _pbr_maps(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("shading.prepare_pbr_maps", {"object": subject})


def _lod(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("object.lod_create", {"object": subject, "ratio": 0.5, "apply": True})


def _collision(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("object.collision_proxy_create", {"object": subject})
    bridge.call("object.collision_hulls_create", {"object": subject})


def _apply_transform(bridge: Any, subject: str, info: dict) -> None:
    bridge.call("object.transform_apply", {"object": subject})


#: (name, gate paths that trigger it, apply)
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

#: Every tool name this module can call (checked registered by tests + the runner guard).
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


def _revert(bridge: Any, subject: str, label: str, objs_before: set[str]) -> None:
    strays = sorted(_scene_objects(bridge) - objs_before)
    if strays:
        bridge.call("object.delete", {"objects": ",".join(strays)})
    bridge.call("session.revert", {"object": subject, "label": label})


def finish(bridge: Any, subject: str, item: dict) -> dict:
    """Runner entrypoint: finish `subject` in place; returns a per-move report."""
    asset_class = item.get("asset_class")
    item_id = str(item.get("id", subject))
    info = {"asset_class": asset_class}
    moves_report: list[dict] = []
    start = _readiness(bridge, subject, asset_class)
    # Cached across SKIPPED moves only; None forces a fresh read after a fired move.
    current: dict | None = start

    for name, paths, apply_move in MOVES:
        before = current if current is not None else _readiness(bridge, subject, asset_class)
        current = before
        if not _failing(before, *paths):
            continue
        label = f"finisher:{name}"
        bridge.call("session.checkpoint", {"object": subject, "label": label})
        objs_before = _scene_objects(bridge)
        current = None  # the move fires: whatever happens next, re-read before the next gate check
        try:
            apply_move(bridge, subject, info)
        except BridgeError as exc:
            _revert(bridge, subject, label, objs_before)
            moves_report.append({"move": name, "kept": False, "error": str(exc)[:120]})
            _log(item_id, f"{name}: ERROR {str(exc)[:80]} -> reverted")
            continue
        after = _readiness(bridge, subject, asset_class)
        r_before = before.get("readiness") or 0.0
        r_after = after.get("readiness") or 0.0
        pres_ok, pres = _preservation_ok(bridge, subject)
        kept = (r_after >= r_before - _EPS) and pres_ok
        if not kept:
            _revert(bridge, subject, label, objs_before)
        moves_report.append({"move": name, "kept": kept,
                             "readiness_before": before.get("readiness"),
                             "readiness_after": after.get("readiness"),
                             "preservation": pres})
        _log(item_id, f"{name}: {_fmt(before.get('readiness'))} -> {_fmt(after.get('readiness'))} "
                      f"pres={_fmt(pres)} {'KEPT' if kept else 'REVERTED'}")

    final = _readiness(bridge, subject, asset_class)
    return {"readiness_start": start.get("readiness"),
            "readiness_final": final.get("readiness"), "moves": moves_report}
