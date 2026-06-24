"""Layer 2 asset-class profiles for deterministic server-side game-asset targets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_ASSET_CLASS = "hard_surface_prop"

_PROFILES: dict[str, dict[str, Any]] = {
    "hard_surface_prop": {
        "id": "hard_surface_prop",
        "profile_version": 1,
        "label": "Hard-surface prop",
        "summary": "Structured hard-surface game prop with clean quad topology and tight collision.",
        "defaults": {
            "triangle_budget": 5000,
            "material_budget": 4,
            "texture_budget": 8,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.75,
            "max_lod_bounds_delta": 0.10,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.50,
            "max_texture_size": 2048,
        },
        "gate_overrides": {},
        "stage_targets": {
            "retopo": "Clean mostly-quad hard-surface topology.",
            "uv": "Packed non-overlapping UVs with controlled stretch.",
            "optimize": "Tight collision and at least one reduced LOD.",
        },
        "guidance": {
            "retopo": "Preserve bevel support loops and flat-panel edge flow.",
            "uv": "Keep seams on hard edges and preserve texel consistency across panels.",
            "optimize": "Use split collision hulls for concave silhouettes instead of one loose box.",
        },
    },
    "organic_prop": {
        "id": "organic_prop",
        "profile_version": 1,
        "label": "Organic prop",
        "summary": "Organic or sculpt-derived prop where silhouette preservation is more important than perfect quads.",
        "defaults": {
            "triangle_budget": 8000,
            "material_budget": 3,
            "texture_budget": 8,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.80,
            "max_lod_bounds_delta": 0.18,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.75,
            "max_texture_size": 2048,
        },
        "gate_overrides": {
            "retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.85}},
            "uv": {"uv.stretch_ratio": {"op": "<=", "value": 2.5}},
        },
        "stage_targets": {
            "retopo": "Mostly quads with enough allowance for organic triangle cleanup.",
            "uv": "Lower visible stretch on curved forms, with relaxed numeric tolerance.",
            "optimize": "Preserve broad silhouette while reducing density.",
        },
        "guidance": {
            "retopo": "Keep loops flowing with anatomy or growth direction; avoid poles on silhouettes.",
            "uv": "Place seams on hidden backsides or natural creases.",
            "optimize": "Prefer LODs that preserve the outer silhouette over aggressive triangle cuts.",
        },
    },
    "generated_cleanup": {
        "id": "generated_cleanup",
        "profile_version": 1,
        "label": "Generated cleanup",
        "summary": "Cleanup pass for generated or scanned meshes that need stricter retopo and UV gates.",
        "defaults": {
            "triangle_budget": 6000,
            "material_budget": 4,
            "texture_budget": 8,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.65,
            "max_lod_bounds_delta": 0.12,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.50,
            "max_texture_size": 2048,
        },
        "gate_overrides": {
            "retopo": {"topology.quad_ratio": {"op": ">=", "value": 0.98}},
            "uv": {"uv.stretch_ratio": {"op": "<=", "value": 1.75}},
        },
        "stage_targets": {
            "retopo": "Strict quad cleanup to remove generated topology noise.",
            "uv": "Strict stretch target so projection cleanup does not hide bad geometry.",
            "optimize": "Aggressive LOD reduction after cleanup stabilizes topology.",
        },
        "guidance": {
            "retopo": "Rebuild noisy generated regions instead of preserving accidental triangulation.",
            "uv": "Reunwrap generated islands; do not trust inherited UVs from cleanup inputs.",
            "optimize": "Use stricter LOD reduction after removing duplicate/generated detail.",
        },
    },
    "from_scratch_prop": {
        "id": "from_scratch_prop",
        "profile_version": 1,
        "label": "From-scratch prop",
        "summary": "Freshly authored prop with tighter budgets because topology and materials are controllable from the start.",
        "defaults": {
            "triangle_budget": 4000,
            "material_budget": 3,
            "texture_budget": 6,
            "min_lods": 1,
            "max_lod_triangle_ratio": 0.75,
            "max_lod_bounds_delta": 0.10,
            "min_collision_hulls": 1,
            "max_collision_oversize_ratio": 0.50,
            "max_texture_size": 2048,
        },
        "gate_overrides": {},
        "stage_targets": {
            "retopo": "Author clean quads directly instead of repairing later.",
            "uv": "Plan seams and trim usage while modeling.",
            "optimize": "Stay inside tighter budgets from the first blockout.",
        },
        "guidance": {
            "retopo": "Keep forms simple and purposeful before adding support loops.",
            "uv": "Lay out trims and seams as part of the modeling plan.",
            "optimize": "Do not spend triangles on details that should be baked or textured.",
        },
    },
}

ASSET_CLASS_IDS = sorted(_PROFILES)
_DEFAULT_KEYS = {"asset_class"}


def list_asset_classes() -> list[dict[str, Any]]:
    return [deepcopy(_PROFILES[name]) for name in ASSET_CLASS_IDS]


def get_asset_class(name: str | None) -> dict[str, Any]:
    asset_class = name if isinstance(name, str) and name else DEFAULT_ASSET_CLASS
    try:
        return deepcopy(_PROFILES[asset_class])
    except KeyError as exc:
        raise KeyError(f"unknown asset class: {asset_class}") from exc


def _class_from_payload_or_state(payload: dict[str, Any], state: dict[str, Any] | None) -> tuple[str, bool]:
    raw = payload.get("asset_class")
    if isinstance(raw, str) and raw:
        return raw, False
    if state is not None:
        stored = state.get("asset_class")
        if isinstance(stored, str) and stored:
            return stored, False
    return DEFAULT_ASSET_CLASS, True


def apply_asset_class_defaults(
    payload: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    asset_class, defaulted = _class_from_payload_or_state(payload, state)
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
