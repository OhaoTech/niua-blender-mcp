"""Layer 2 asset-class profiles for deterministic game-asset targets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_ASSET_CLASS = "hard_surface_prop"

_BASE_DEFAULTS = {
    "triangle_budget": 5000, "material_budget": 4, "texture_budget": 8,
    "min_lods": 1, "max_lod_triangle_ratio": 0.75, "max_lod_bounds_delta": 0.10,
    "min_collision_hulls": 1, "max_collision_oversize_ratio": 0.50, "max_texture_size": 2048,
}


def _profile(pid, label, summary, defaults_delta=None, gate_overrides=None):
    return {
        "id": pid, "profile_version": 1, "label": label, "summary": summary,
        "defaults": {**_BASE_DEFAULTS, **(defaults_delta or {})},
        "gate_overrides": gate_overrides or {},
    }


_PROFILES: dict[str, dict[str, Any]] = {
    "hard_surface_prop": _profile(
        "hard_surface_prop", "Hard-surface prop",
        "Structured hard-surface game prop with clean quad topology and tight collision."),
    "organic_prop": _profile(
        "organic_prop", "Organic prop",
        "Organic or sculpt-derived prop where silhouette preservation is more important than perfect quads.",
        {"triangle_budget": 8000, "material_budget": 3, "max_lod_triangle_ratio": 0.80,
         "max_lod_bounds_delta": 0.18, "max_collision_oversize_ratio": 0.75},
        {"retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.85}},
         "uv": {"uv.stretch_ratio": {"op": "<=", "value": 2.5}}}),
    "generated_cleanup": _profile(
        "generated_cleanup", "Generated cleanup",
        "Cleanup pass for generated or scanned meshes that need stricter retopo and UV gates.",
        {"triangle_budget": 6000, "max_lod_triangle_ratio": 0.65, "max_lod_bounds_delta": 0.12},
        {"retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.98}},
         "uv": {"uv.stretch_ratio": {"op": "<=", "value": 1.75}}}),
    "from_scratch_prop": _profile(
        "from_scratch_prop", "From-scratch prop",
        "Freshly authored prop with tighter budgets because topology and materials are controllable from the start.",
        {"triangle_budget": 4000, "material_budget": 3, "texture_budget": 6}),
    "character": _profile(
        "character", "Character",
        "Rigged/animated game character; higher triangle budget than a prop because silhouette + surface read at close range.",
        {"triangle_budget": 18000, "material_budget": 4, "texture_budget": 8,
         "max_lod_triangle_ratio": 0.6, "max_lod_bounds_delta": 0.12}),
}

ASSET_CLASS_IDS = sorted(_PROFILES)


def list_asset_classes() -> list[dict[str, Any]]:
    return [deepcopy(_PROFILES[name]) for name in ASSET_CLASS_IDS]


def get_asset_class(name: str | None) -> dict[str, Any]:
    asset_class = name if isinstance(name, str) and name else DEFAULT_ASSET_CLASS
    try:
        return deepcopy(_PROFILES[asset_class])
    except KeyError as exc:
        raise KeyError(f"unknown asset class: {asset_class}") from exc


def apply_asset_class_defaults(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = payload.get("asset_class")
    asset_class = raw if isinstance(raw, str) and raw else DEFAULT_ASSET_CLASS
    defaulted = not (isinstance(raw, str) and raw)
    profile = get_asset_class(asset_class)
    merged = dict(payload)
    effective_defaults: dict[str, Any] = {}
    for key, value in profile["defaults"].items():
        if key not in merged or merged[key] is None:
            merged[key] = value
        effective_defaults[key] = merged[key]
    merged["asset_class"] = profile["id"]
    meta = {
        "id": profile["id"],
        "profile_version": profile["profile_version"],
        "label": profile["label"],
        "summary": profile["summary"],
        "asset_class_defaulted": defaulted,
        "effective_defaults": effective_defaults,
        "applied_gate_overrides": {},
    }
    return merged, meta


def apply_gate_overrides(
    gates: list[dict[str, Any]],
    profile: dict[str, Any],
    stage: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = [deepcopy(gate) for gate in gates]
    overrides = deepcopy(profile.get("gate_overrides", {}).get(stage, {}))
    if not overrides:
        return out, {}
    by_path = {gate["path"]: gate for gate in out}
    for path, replacement in overrides.items():
        if path not in by_path:
            raise ValueError(f"invalid gate override path for {stage}: {path}")
        by_path[path].update({"op": replacement["op"], "value": replacement["value"]})
    return out, {stage: overrides}
