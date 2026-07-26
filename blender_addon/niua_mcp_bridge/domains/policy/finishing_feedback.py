"""Finishing feedback: the agent's policy-laden judgment channel.

The five ``feedback.*`` policy tools (moved out of ``domains/feedback.py``, which keeps
the generic capture/capture_views/silhouette/turntable eyes) plus ``io.profile_validate``
(moved out of ``domains/io.py``, whose other handlers only ever touch files). All six
encode NIUA game-asset policy -- asset-class budgets, objective gate definitions,
export-profile conventions, do-no-harm preservation -- so they live in the finishing
layer and import from ``..finishing`` freely. That import direction (finishing ->
interface) is allowed; the reverse is not.

* ``feedback.quality`` -- objective quality metrics for a mesh: topology, UVs,
  orientation, symmetry, proportion, scale, engine/material/export-profile readiness.
* ``feedback.critique`` -- the one OBSERVE call the agent uses to *judge*: multi-angle
  images AND the analytic mesh/UV/quality report in a single bundle.
* ``feedback.capture_intake`` -- records the do-no-harm baseline: fixed-frame ortho alpha
  silhouette masks + the intake bbox, written to the passive
  ``finishing/preservation_ledger.py`` scratchpad (NOT the pipeline FSM) for later
  preservation checks.
* ``feedback.preservation`` -- do-no-harm metric: silhouette IoU of the current form vs
  the stored intake baseline, plus a GL-free bbox delta.
* ``feedback.readiness`` -- the objective game-ready scorecard: fraction of ALL objective
  gate groups passed, aggregated in NO ORDER. Reuses the gate *definitions*
  (``finishing/gates.{stage_gates,check_gates,gate_profile}``) and ``feedback.quality``.
* ``io.profile_validate`` -- validates an object against a named export profile
  (``finishing/export_profiles.py``) without exporting anything.

Shared geometry helpers (``_proportion``, ``_symmetry``) are used by BOTH this module
and the generic ``domains/feedback.py`` (``feedback.silhouette``), so they stay defined
in ``feedback.py`` and are imported here -- finishing importing interface is allowed.
"""

from __future__ import annotations

from typing import Any

from ...context import Ctx
from ...core import fidelity_metrics as _fm
from ...core import session as _session
from ...core import silhouette as _sil
from ...core import silhouette_metrics as _sm
from ...core.orientation_metrics import orientation_quality
from ...dispatch import Command
from ...errors import INVALID_PARAMS, PRECONDITION, BridgeError
from ...finishing import asset_classes
from ...finishing import preservation_ledger as _ledger
from ...finishing.engine_metrics import engine_quality
from ...finishing.export_profiles import export_profile_quality
from ...finishing.gates import check_gates, gate_profile, stage_gates
from ...finishing.material_metrics import material_quality
from ..feedback import _proportion, _symmetry
from ..mesh import (
    _bmesh_for,
    _resolve_mesh,
    bbox_dimensions,
    report as mesh_report,
    topology_counts,
    transform_applied,
)
from ..uv import report as uv_report


def capture_intake(ctx: Ctx, payload: dict) -> dict:
    """Record the intake do-no-harm baseline: fixed-frame ortho alpha masks + bbox + checkpoint.

    Read-only (mutates=False): renders, copies a datablock (session.checkpoint), and writes the
    passive ledger -- none of which changes the visible scene. Fail-closed: if any view is not
    cleanly separable, the baseline is stored unavailable so preservation reports 'unmeasured'
    rather than trusting a degenerate capture. The ledger is a thin per-object scratchpad, NOT
    the pipeline FSM (finishing/preservation_ledger.py holds no stage/order/progress state).
    """
    obj = _resolve_mesh(ctx, payload)
    out = _sil.render_preservation_views(
        ctx.bpy, obj.name, views=_ledger.PRESERVATION_VIEWS, res=_ledger.PRESERVATION_RES
    )
    if not out.get("available"):
        _ledger.set_intake(obj.name, {"available": False, "reason": out.get("reason", "unavailable")})
        return {"object": obj.name, "available": False, "reason": out.get("reason", "unavailable")}

    masks: dict[str, str] = {}
    coverage: dict[str, float] = {}
    shape = None
    for img in out.get("images", []):
        try:
            w, h, mask = _sm.png_b64_to_mask(img["data"])
        except Exception:  # noqa: BLE001 - a bad view fails the whole baseline (fail-closed)
            _ledger.set_intake(obj.name, {"available": False, "reason": "decode failed"})
            return {"object": obj.name, "available": False, "reason": "decode failed"}
        if not _sm.is_separable(mask):
            _ledger.set_intake(obj.name, {"available": False, "reason": f"{img['view']} not separable"})
            return {"object": obj.name, "available": False, "reason": f"{img['view']} not separable"}
        masks[img["view"]] = _sm.compact_encode(mask)
        coverage[img["view"]] = _sm.mask_coverage(mask)
        shape = [h, w]

    shaded = None
    try:
        fout = _sil.render_fidelity_views(ctx.bpy, obj.name, frame=out.get("frame"),
                                          views=_ledger.PRESERVATION_VIEWS, res=_ledger.PRESERVATION_RES)
        if fout.get("available"):
            sviews = {}
            for img in fout.get("images", []):
                fw, fh, luma, fmask = _fm.png_b64_to_luma_mask(img["data"])
                sviews[img["view"]] = {"luma": _sm.compact_encode(luma), "mask": _sm.compact_encode(fmask)}
            if sviews:
                shaded = {"views": sviews, "shape": [fh, fw], "frame": fout.get("frame")}
    except Exception:  # noqa: BLE001 - fidelity is additive; never break the silhouette baseline
        shaded = None

    _session.checkpoint(obj, label="mcp:intake")
    _ledger.set_intake(obj.name, {
        "available": True, "res": out["res"], "frame": out["frame"],
        "size": out["measured"]["size"], "masks": masks, "shape": shape,
        "coverage": coverage, "checkpoint_label": "mcp:intake", "shaded": shaded,
    })
    return {"object": obj.name, "available": True, "views": sorted(masks),
            "coverage": coverage, "checkpoint_label": "mcp:intake"}


def preservation(ctx: Ctx, payload: dict) -> dict:
    """Do-no-harm METRIC (read-only): mean/min silhouette IoU of current form vs stored intake,
    plus a GL-free bbox scale/aspect delta. Measures and reports; it never reverts anything and
    touches no pipeline state -- `harm_flagged` is applied downstream by the scorecard, not here.
    """
    obj = _resolve_mesh(ctx, payload)
    rec = _ledger.get_intake(obj.name)
    if rec is None:
        raise BridgeError(PRECONDITION, f"no intake baseline; call feedback.capture_intake for {obj.name}")
    floor = _ledger.PRESERVATION_FLOOR
    if not rec.get("available"):
        return {"object": obj.name, "available": False, "preservation": None,
                "preservation_pass": False, "threshold": floor,
                "reason": rec.get("reason", "intake baseline unavailable")}

    cur = _sil.render_preservation_views(
        ctx.bpy, obj.name, frame=rec["frame"], views=tuple(rec["masks"]), res=rec["res"]
    )
    if not cur.get("available"):
        return {"object": obj.name, "available": False, "preservation": None,
                "preservation_pass": False, "threshold": floor,
                "reason": cur.get("reason", "current silhouette unavailable")}

    intake_masks = {v: _sm.compact_decode(d) for v, d in rec["masks"].items()}
    current_masks: dict[str, bytes] = {}
    for img in cur.get("images", []):
        try:
            current_masks[img["view"]] = _sm.png_b64_to_mask(img["data"])[2]
        except Exception:  # noqa: BLE001
            continue
    metric = _sm.mean_preservation(intake_masks, current_masks)
    delta = _sm.bbox_delta(rec["size"], cur["measured"]["size"])
    score = metric.get("preservation") if metric.get("available") else None

    surface = {"available": False, "fidelity": None, "per_view": {}, "min_view": None}
    sh = rec.get("shaded")
    if sh:
        try:
            fcur = _sil.render_fidelity_views(ctx.bpy, obj.name, frame=sh.get("frame"),
                                              views=tuple(sh["views"]), res=rec["res"])
            if fcur.get("available"):
                fh, fw = sh["shape"]
                intake_lm = {v: (fw, fh, _sm.compact_decode(d["luma"]), _sm.compact_decode(d["mask"]))
                             for v, d in sh["views"].items()}
                cur_lm = {}
                for img in fcur.get("images", []):
                    cw, ch2, luma, cmask = _fm.png_b64_to_luma_mask(img["data"])
                    cur_lm[img["view"]] = (cw, ch2, luma, cmask)
                surface = _fm.mean_fidelity(intake_lm, cur_lm)
        except Exception:  # noqa: BLE001 - fail-closed: fidelity unmeasured, never a fake score
            surface = {"available": False, "fidelity": None, "per_view": {}, "min_view": None}

    if surface.get("available"):
        sf_score = surface.get("fidelity")
        surface["surface_fidelity_pass"] = sf_score is not None and sf_score >= _ledger.SURFACE_FIDELITY_FLOOR
        surface["floor"] = _ledger.SURFACE_FIDELITY_FLOOR

    return {
        "object": obj.name,
        "available": bool(metric.get("available")),
        "preservation": score,
        "preservation_pass": bool(metric.get("available")) and score is not None and score >= floor,
        "threshold": floor,
        "per_view": metric.get("per_view", {}),
        "min_view": metric.get("min_view"),
        "bbox_delta": delta,
        "surface_fidelity": surface,
    }


# All objective gate groups, aggregated in NO ORDER (this is a set to check, not a walk).
_GATE_GROUPS = ["repair", "retopo", "uv", "bake", "material", "optimize", "export_preflight"]


def _hashable(v: Any) -> Any:
    return tuple(v) if isinstance(v, (list, dict, set)) else v


def readiness(ctx: Ctx, payload: dict) -> dict:
    """Objective game-readiness scorecard (read-only): fraction of gates passed across every gate
    group, aggregated with no order. Reports BOTH the deduped-gate fraction (headline) and the
    mean per-group pass-fraction, so a group with many gates (optimize=9) can't skew the reading
    and a path shared by two groups isn't double-counted. Reuses feedback.quality + the objective
    gate definitions (``finishing/gates.{stage_gates,check_gates,gate_profile}``) -- no judge, no
    images, no pipeline state; this is the order-free replacement for the FSM's single-file gate
    march, not a walk over it.
    """
    obj = _resolve_mesh(ctx, payload)
    asset_class = payload.get("asset_class")
    metrics = quality(ctx, {"object": obj.name, "asset_class": asset_class} if asset_class
                      else {"object": obj.name})
    asset_meta = metrics.get("asset_class", {})
    ac_id = asset_meta.get("id") if isinstance(asset_meta, dict) else asset_class

    per_group: list[dict] = []
    deduped: dict[tuple, tuple[Any, bool]] = {}   # (path, op, value) -> (actual, pass) (kept once)
    stage_fractions: list[float] = []
    for group in _GATE_GROUPS:
        gates, _applied = stage_gates(group, asset_class=ac_id)
        if not gates:
            continue
        checked = check_gates(metrics, gates)
        count = len(gates)
        passed = sum(1 for g in checked["gates"] if g["pass"])
        stage_fractions.append(passed / count)
        per_group.append({"group": group, "gate_profile": gate_profile(group),
                          "gates_pass": checked["gates_pass"], "gates_count": count,
                          "gates_pass_count": passed, "pass_fraction": passed / count})
        for g in checked["gates"]:
            deduped[(g["path"], g["op"], _hashable(g["value"]))] = (g["actual"], g["pass"])

    total = len(deduped)
    total_pass = sum(1 for _actual, ok in deduped.values() if ok)
    per_gate = [{"path": p, "op": o, "value": v, "actual": actual, "pass": ok}
                for (p, o, v), (actual, ok) in deduped.items()]
    return {
        "object": obj.name, "asset_class": asset_meta,
        "readiness": (total_pass / total) if total else None,
        "stage_pass_fraction_mean": (sum(stage_fractions) / len(stage_fractions)) if stage_fractions else None,
        "total_gates_deduped": total, "total_gates_pass_deduped": total_pass,
        "per_group": per_group, "per_gate": per_gate,
    }


def _loose_verts(bm: Any) -> int:
    """Verts with no linked edges (orphan geometry)."""
    return sum(1 for v in bm.verts if len(v.link_edges) == 0)


def _pole_count(bm: Any) -> int:
    """Interior verts whose edge valence != 4 (poles); boundary verts are excluded.

    A boundary vert (touching a non-manifold/border edge) naturally has valence != 4 and
    is not a topology defect, so it must not be counted as a pole.
    """
    poles = 0
    for v in bm.verts:
        if any(not e.is_manifold for e in v.link_edges):
            continue  # boundary / non-manifold vert: not a pole
        if len(v.link_edges) != 4:
            poles += 1
    return poles


def _topology_quality(obj: Any, counts: dict) -> dict:
    """Topology block: face-count metrics (always) + bmesh-derived metrics (or null)."""
    pole_count: int | None = None
    non_manifold_edges: int | None = None
    loose_verts: int | None = None
    bm = _bmesh_for(obj)
    if bm is not None:
        try:
            pole_count = _pole_count(bm)
            non_manifold_edges = sum(1 for e in bm.edges if not e.is_manifold)
            loose_verts = _loose_verts(bm)
        finally:
            bm.free()
    return {
        "faces": counts["faces"],
        "tris": counts["tris"],
        "quads": counts["quads"],
        "ngons": counts["ngons"],
        "quad_ratio": counts["quad_ratio"],
        "ngon_ratio": counts["ngon_ratio"],
        "pole_count": pole_count,
        "non_manifold_edges": non_manifold_edges,
        "loose_verts": loose_verts,
    }


def _scale(obj: Any) -> dict:
    return {
        "bbox_dimensions": bbox_dimensions(obj),
        "transform_applied": transform_applied(obj),
    }


def quality(ctx: Ctx, payload: dict) -> dict:
    """Objective quality metrics for a mesh: topology, UVs, orientation, symmetry, proportion, scale, engine/material readiness.

    The numeric judgment channel that complements the multi-angle images -- so the agent's
    do->observe->judge->revert loop converges on facts, not vibes. Read-only; bmesh-derived
    fields (pole_count, non_manifold_edges, loose_verts) degrade to ``null`` without bmesh.
    """
    obj = _resolve_mesh(ctx, payload)
    try:
        # Resolve asset_class from the payload only -- the pipeline FSM that once threaded
        # a stored asset_class through here is gone (deleted in Task 4).
        effective_payload, asset_meta = asset_classes.apply_asset_class_defaults(payload)
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc
    mesh = obj.data
    counts = topology_counts(mesh)
    return {
        "object": obj.name,
        "asset_class": asset_meta,
        "topology": _topology_quality(obj, counts),
        "uv": uv_report(ctx, {"object": obj.name}),
        "orientation": orientation_quality(obj),
        "symmetry": _symmetry(mesh),
        "proportion": _proportion(obj),
        "scale": _scale(obj),
        "engine": engine_quality(ctx, obj, counts, effective_payload),
        "material": material_quality(obj, effective_payload),
        "export_profile": export_profile_quality(ctx, obj, counts, effective_payload),
    }


def _quality_compact(ctx: Ctx, obj_name: Any) -> dict | None:
    """A compact quality sub-dict for folding into ``critique`` (best-effort, never raises)."""
    try:
        full = quality(ctx, {"object": obj_name} if obj_name else {})
    except Exception:  # noqa: BLE001 - non-mesh / no-object: critique stays usable
        return None
    topo = full["topology"]
    return {
        "quad_ratio": topo["quad_ratio"],
        "ngon_ratio": topo["ngon_ratio"],
        "pole_count": topo["pole_count"],
        "non_manifold_edges": topo["non_manifold_edges"],
        "loose_verts": topo["loose_verts"],
        "uv": full["uv"],
        "orientation": full["orientation"],
        "symmetry": full["symmetry"],
        "aspect_ratio": full["proportion"]["aspect_ratio"],
        "transform_applied": full["scale"]["transform_applied"],
        "asset_class": full["asset_class"],
        "engine": full["engine"],
        "material": full["material"],
        "export_profile": full["export_profile"],
    }


def critique(ctx: Ctx, payload: dict) -> dict:
    """The one observe call to judge a model: multi-angle images + analytic report.

    Bundles ``feedback.capture_views`` (taste signal -- the anti-blob) with ``mesh.report``
    (checkable facts), a compact ``quality`` sub-dict (the objective judgment channel:
    quad/n-gon ratios, poles, non-manifold, symmetry, aspect) and, for a mesh, ``uv.report``.
    The agent is the critic: it reads silhouette/proportion from the images and
    topology/symmetry/scale from the numbers, then keeps or reverts. Read-only; degrades to
    ``available: false`` images on a headless/no-GPU box while the analytic half still comes
    back.
    """
    from ...core import capture as cap

    obj = payload.get("object")
    preset = str(payload.get("preset", "ortho4"))
    shading = str(payload.get("shading", "SOLID"))
    res = int(payload.get("res", 640))

    views = cap.capture_views(ctx.bpy, preset=preset, shading=shading, res=res, obj_name=obj)

    report: dict[str, Any] | None = None
    uv: dict[str, Any] | None = None
    is_mesh = False
    try:
        report = mesh_report(ctx, {"object": obj} if obj else {})
        is_mesh = True
    except Exception as exc:  # noqa: BLE001 - non-mesh / no-object: report stays null
        report = {"available": False, "reason": str(exc)}
    if is_mesh:
        # Fold a compact objective-quality block into the report so one observe call gives
        # images + counts + quality.
        compact = _quality_compact(ctx, obj)
        if compact is not None:
            report["quality"] = compact
        try:
            uv = uv_report(ctx, {"object": obj} if obj else {})
        except Exception:  # noqa: BLE001 - keep the bundle even if UV introspection trips
            uv = None

    return {
        "available": views.get("available", False),
        "images": views.get("images", []),
        "report": report,
        "uv": uv,
    }


def profile_validate(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("object")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    obj = ctx.get_object(name)
    counts = topology_counts(getattr(obj, "data", None))
    out = export_profile_quality(ctx, obj, counts, payload)
    return {"object": getattr(obj, "name", ""), **out}


COMMANDS = [
    Command("feedback.critique", critique, mutates=False, timeout_tier="heavy"),
    Command("feedback.quality", quality, mutates=False, timeout_tier="heavy"),
    Command("feedback.capture_intake", capture_intake, mutates=False, timeout_tier="heavy"),
    Command("feedback.preservation", preservation, mutates=False, timeout_tier="heavy"),
    Command("feedback.readiness", readiness, mutates=False, timeout_tier="heavy"),
    Command("io.profile_validate", profile_validate, mutates=False),
]
