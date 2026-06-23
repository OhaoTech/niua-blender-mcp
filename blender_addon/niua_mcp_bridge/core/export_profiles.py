"""Parameterized export profile validation for Layer 2 export preflight."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .engine_metrics import engine_quality

_SAFE_NAME = r"^[A-Za-z0-9_.-]+$"

_PROFILES: dict[str, dict[str, Any]] = {
    "GENERIC": {
        "allowed_formats": ["GLB", "GLTF_SEPARATE", "FBX", "OBJ"],
        "name_regex": _SAFE_NAME,
        "require_applied_transforms": True,
        "y_up": None,
        "min_lods": 0,
        "require_collision": False,
    },
    "GODOT": {
        "allowed_formats": ["GLB", "GLTF_SEPARATE"],
        "name_regex": _SAFE_NAME,
        "require_applied_transforms": True,
        "y_up": True,
        "min_lods": 1,
        "require_collision": True,
    },
    "UNREAL": {
        "allowed_formats": ["FBX", "GLB"],
        "name_regex": _SAFE_NAME,
        "require_applied_transforms": True,
        "y_up": False,
        "min_lods": 1,
        "require_collision": True,
    },
    "CUSTOM": {
        "allowed_formats": ["GLB"],
        "name_regex": _SAFE_NAME,
        "require_applied_transforms": True,
        "y_up": None,
        "min_lods": 0,
        "require_collision": False,
    },
}


def _is_identity(matrix: Any, eps: float = 1e-5) -> bool:
    try:
        rows = [[float(value) for value in row] for row in matrix]
    except Exception:  # noqa: BLE001
        return False
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        return False
    for row in range(4):
        for col in range(4):
            expected = 1.0 if row == col else 0.0
            if abs(rows[row][col] - expected) > eps:
                return False
    return True


def _bool_value(payload: dict[str, Any], key: str, default: bool) -> bool:
    return bool(payload[key]) if key in payload and payload[key] is not None else default


def _int_value(payload: dict[str, Any], key: str, default: int) -> int:
    return int(payload[key]) if key in payload and payload[key] is not None else default


def _parse_formats(raw: Any, default: list[str]) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return list(default)
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


def _payload_value(payload: dict[str, Any], primary: str, fallback: str, default: Any) -> Any:
    if primary in payload and payload[primary] is not None:
        return payload[primary]
    if fallback in payload and payload[fallback] is not None:
        return payload[fallback]
    return default


def _profile_options(payload: dict[str, Any]) -> dict[str, Any]:
    profile = str(_payload_value(payload, "export_profile", "profile", "GENERIC")).upper()
    if profile not in _PROFILES:
        profile = "GENERIC"
    options = deepcopy(_PROFILES[profile])
    options["profile"] = profile
    if profile == "CUSTOM":
        options["allowed_formats"] = _parse_formats(payload.get("allowed_formats"), options["allowed_formats"])
        if "name_regex" in payload and payload["name_regex"]:
            options["name_regex"] = str(payload["name_regex"])
        options["require_applied_transforms"] = _bool_value(
            payload, "require_applied_transforms", bool(options["require_applied_transforms"])
        )
        options["require_collision"] = _bool_value(payload, "require_collision", bool(options["require_collision"]))
        options["min_lods"] = _int_value(payload, "min_lods", int(options["min_lods"]))
    return options


def _check(path: str, actual: Any, expected: Any, passed: bool) -> dict[str, Any]:
    return {"path": path, "actual": actual, "expected": expected, "pass": bool(passed)}


def _name_matches_check(name: str, pattern: str) -> dict[str, Any]:
    try:
        passed = re.fullmatch(pattern, name) is not None
    except re.error as exc:
        check = _check("export_profile.name_matches", name, pattern, False)
        check["error"] = "invalid_regex"
        check["message"] = str(exc)
        return check
    return _check("export_profile.name_matches", name, pattern, passed)


def export_profile_quality(
    ctx: Any,
    obj: Any,
    counts: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    options = _profile_options(payload)
    fmt = str(_payload_value(payload, "export_format", "format", "GLB")).upper()
    actual_y_up = _payload_value(payload, "export_y_up", "y_up", options.get("y_up"))
    if actual_y_up is not None:
        actual_y_up = bool(actual_y_up)

    name = str(getattr(obj, "name", ""))
    transform_applied = _is_identity(getattr(obj, "matrix_world", None))
    engine = engine_quality(ctx, obj, counts, {"min_lods": options["min_lods"]})
    checks = [
        _check(
            "export_profile.format_allowed",
            fmt,
            options["allowed_formats"],
            fmt in options["allowed_formats"],
        ),
        _name_matches_check(name, options["name_regex"]),
        _check(
            "export_profile.transform_applied",
            transform_applied,
            True,
            transform_applied or not options["require_applied_transforms"],
        ),
    ]
    if options["y_up"] is not None:
        checks.append(
            _check(
                "export_profile.axis_matches",
                actual_y_up,
                {"y_up": options["y_up"]},
                actual_y_up == options["y_up"],
            )
        )
    if options["min_lods"] > 0:
        checks.append(
            _check(
                "export_profile.lod_count",
                engine["lod_count"],
                {">=": options["min_lods"]},
                engine["lod_count"] >= options["min_lods"],
            )
        )
    if options["require_collision"]:
        checks.append(
            _check(
                "export_profile.has_collision_proxy",
                engine["has_collision_proxy"],
                True,
                engine["has_collision_proxy"],
            )
        )
    return {
        "profile": options["profile"],
        "format": fmt,
        "y_up": actual_y_up,
        "profile_pass": all(check["pass"] for check in checks),
        "checks": checks,
        "conventions": {
            "allowed_formats": list(options["allowed_formats"]),
            "name_regex": options["name_regex"],
            "require_applied_transforms": options["require_applied_transforms"],
            "y_up": options["y_up"],
            "min_lods": options["min_lods"],
            "require_collision": options["require_collision"],
        },
    }
