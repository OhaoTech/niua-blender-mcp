"""Deterministic objective benchmark scoring -- no LLM judge.

readiness (order-free deduped gate fraction) and preservation (mean silhouette IoU vs the
stored intake baseline) are computed by the `feedback.readiness` / `feedback.preservation`
tools; this module only scores + aggregates what those tools already measured. Do-no-harm is
a FLAG (`harm_flagged`), never a revert -- that loop lives in prose in `prompts.py`, and as a
deterministic reference implementation (checkpoint/measure/keep-or-revert per move) in
`evals/finisher.py`, not here.

UNMEASURED is not FAILED. A headless render, a missing intake baseline, a non-separable mask,
or (defensively) a readiness read with no applicable gates all produce ``None`` from the live
tools rather than a real 0.0 score. `preservation_measured` / `readiness_measured` carry that
distinction through to `aggregate_objective`, which excludes unmeasured items from the
corresponding mean instead of silently coercing `None` to 0 and reporting it as a failure.
`godot_import` follows the same rule: no binary / no export = unmeasured `None`, never a fake
fail. `surface_fidelity` follows it too: no shaded-render / no intake baseline = unmeasured
`None`, never a fake fail -- and `harm_flagged` fires when EITHER the silhouette-based
`preservation` axis OR this fidelity axis is measured and below its floor.
"""

from __future__ import annotations

from typing import Any

PRESERVATION_FLOOR_DEFAULT = 0.85
SURFACE_FIDELITY_FLOOR_DEFAULT = 0.60


def _num(x: Any) -> float:
    return float(x) if isinstance(x, (int, float)) else 0.0


def score_item_objective(
    item: dict,
    *,
    readiness: float | None,
    stage_pass_fraction: float | None,
    preservation: float | None,
    preservation_available: bool,
    floor: float = PRESERVATION_FLOOR_DEFAULT,
    godot_import: dict | None = None,
    surface_fidelity: float | None = None,
    surface_fidelity_available: bool = False,
    fidelity_floor: float = SURFACE_FIDELITY_FLOOR_DEFAULT,
) -> dict:
    """Score one benchmark item from already-measured readiness + preservation readings.

    `preservation_measured` is True only when the caller reports the metric available AND a
    numeric score came back (a headless run or a non-separable intake yields `preservation=None`
    / `preservation_available=False`, which must NOT be read as harm). `readiness_measured`
    guards the same way for readiness (normally always measurable -- pure mesh geometry -- but
    a `None` from `feedback.readiness` (e.g. no applicable gates for an unknown asset class) is
    still reported honestly rather than silently becoming a 0.0 failure).

    `godot_import` is a third, separate axis (never folded into readiness/preservation so
    pre/post baseline numbers stay comparable): the caller passes the dict returned by
    `evals.godot_roundtrip.verify_gltf_import` (or `None` if the round-trip was skipped). It is
    "measured" only when `godot_import["available"]` is truthy; otherwise `godot_import_ok` is
    `None` (unmeasured), never a fake `False`.

    `surface_fidelity` is a fourth, additive axis (shaded-render block-SSIM vs the intake
    baseline, distinct from the silhouette-IoU `preservation` axis above): "measured" only when
    `surface_fidelity_available` is truthy AND a numeric score came back, mirroring the
    `preservation`/`godot_import` unmeasured-is-`None` rule. Do-no-harm now fires when EITHER
    the silhouette axis OR the fidelity axis is measured-and-below-its-floor -- a decimate that
    keeps the silhouette but destroys surface detail must still flag harm.

    No all-gate `success` boolean: the two continuous axes (`readiness`, `preservation`) are the
    headline, plus the do-no-harm `harm_flagged` and the informational `fully_ready`.
    """
    readiness_measured = readiness is not None
    preservation_measured = bool(preservation_available) and preservation is not None
    godot_measured = bool(godot_import and godot_import.get("available"))
    fid_measured = bool(surface_fidelity_available) and surface_fidelity is not None
    fid_harm = fid_measured and surface_fidelity < fidelity_floor
    return {
        "id": item.get("id"),
        "asset_class": item.get("asset_class"),
        "readiness": readiness if readiness_measured else None,
        "readiness_measured": readiness_measured,
        "stage_pass_fraction": stage_pass_fraction if readiness_measured else None,
        "preservation": preservation if preservation_measured else None,
        "preservation_measured": preservation_measured,
        "preservation_pass": preservation_measured and preservation >= floor,
        "harm_flagged": (preservation_measured and preservation < floor) or fid_harm,
        "fully_ready": readiness_measured and readiness == 1.0,
        "godot_import_ok": bool(godot_import.get("ok")) if godot_measured else None,
        "godot_import_measured": godot_measured,
        "surface_fidelity": surface_fidelity if fid_measured else None,
        "surface_fidelity_measured": fid_measured,
    }


def aggregate_objective(cards: list[dict], floor: float = PRESERVATION_FLOOR_DEFAULT) -> dict:
    """Aggregate objective cards into a scorecard. Unmeasured items are excluded from the
    corresponding mean (never coerced to 0), and their count is reported so a caller can see
    exactly how much of the reading is missing rather than assume the missing part is 0.

    `valid = n_unmeasured == 0` (preservation axis): a headless / no-baseline live run cannot
    masquerade as a clean primary reading -- callers should treat an invalid aggregate as
    non-primary and investigate rather than trust `mean_preservation`.
    """
    n = len(cards)
    pres_measured = [c for c in cards if c.get("preservation_measured")]
    ready_measured = [c for c in cards if c.get("readiness_measured")]

    mean_r = (
        sum(_num(c.get("readiness")) for c in ready_measured) / len(ready_measured)
        if ready_measured
        else None
    )
    mean_s = (
        sum(_num(c.get("stage_pass_fraction")) for c in ready_measured) / len(ready_measured)
        if ready_measured
        else None
    )
    mean_p = (
        sum(c["preservation"] for c in pres_measured) / len(pres_measured)
        if pres_measured
        else None
    )
    fid_measured = [c for c in cards if c.get("surface_fidelity_measured")]
    mean_fid = (
        sum(c["surface_fidelity"] for c in fid_measured) / len(fid_measured)
        if fid_measured
        else None
    )

    per_class: dict[str, dict] = {}
    for c in cards:
        bucket = per_class.setdefault(c["asset_class"], {"n": 0, "_r": [], "_pm": [], "n_harm": 0})
        bucket["n"] += 1
        bucket["n_harm"] += 1 if c.get("harm_flagged") else 0
        if c.get("readiness_measured"):
            bucket["_r"].append(_num(c.get("readiness")))
        if c.get("preservation_measured"):
            bucket["_pm"].append(c["preservation"])
    for bucket in per_class.values():
        r_list = bucket.pop("_r")
        bucket["mean_readiness"] = (sum(r_list) / len(r_list)) if r_list else None
        p_list = bucket.pop("_pm")
        bucket["mean_preservation"] = (sum(p_list) / len(p_list)) if p_list else None

    return {
        "n_items": n,
        "n_measured": len(pres_measured),
        "n_unmeasured": n - len(pres_measured),
        "n_readiness_measured": len(ready_measured),
        "n_readiness_unmeasured": n - len(ready_measured),
        "n_harm_flagged": sum(1 for c in cards if c.get("harm_flagged")),
        "n_preservation_pass": sum(1 for c in cards if c.get("preservation_pass")),
        "n_fully_ready": sum(1 for c in cards if c.get("fully_ready")),
        "mean_readiness": mean_r,
        "mean_stage_pass_fraction": mean_s,
        "mean_preservation": mean_p,
        "floor": floor,
        "per_class": per_class,
        "valid": n > 0 and (n - len(pres_measured)) == 0,
        "n_godot_measured": sum(1 for c in cards if c.get("godot_import_measured")),
        "n_godot_import_ok": sum(1 for c in cards if c.get("godot_import_ok")),
        "mean_surface_fidelity": mean_fid,
        "n_fidelity_measured": len(fid_measured),
    }
