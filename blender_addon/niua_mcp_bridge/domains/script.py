"""Script space GUI-parity handlers."""

from __future__ import annotations

import os
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, PRECONDITION, PYTHON_DISABLED, BridgeError

_SCRIPT_OPERATORS = ("python_file_run", "reload", "execute_preset")


def _items(value: Any) -> list[Any]:
    try:
        return list(value or [])
    except TypeError:
        return []


def _name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(getattr(value, "name", "") or "")
    return text or None


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, set):
        return sorted(_json_value(item) for item in value)
    try:
        return [_json_value(item) for item in value]
    except TypeError:
        return str(value)


def _preferences(ctx: Ctx) -> dict[str, Any]:
    filepaths = getattr(getattr(getattr(ctx.bpy, "context", None), "preferences", None), "filepaths", None)
    return {
        "use_scripts_auto_execute": bool(getattr(filepaths, "use_scripts_auto_execute", False)),
    }


def _script_directories(ctx: Ctx) -> list[dict[str, Any]]:
    filepaths = getattr(getattr(getattr(ctx.bpy, "context", None), "preferences", None), "filepaths", None)
    directories = []
    for item in _items(getattr(filepaths, "script_directories", [])):
        directories.append(
            {
                "name": str(getattr(item, "name", "") or ""),
                "directory": str(getattr(item, "directory", "") or ""),
            }
        )
    return directories


def _spaces(ctx: Ctx) -> list[dict[str, Any]]:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    wm = getattr(bpy_ctx, "window_manager", None)
    records: list[dict[str, Any]] = []
    for window_index, window in enumerate(_items(getattr(wm, "windows", []))):
        screen = getattr(window, "screen", None)
        workspace = getattr(window, "workspace", None) or getattr(bpy_ctx, "workspace", None)
        for area_index, area in enumerate(_items(getattr(screen, "areas", []))):
            if str(getattr(area, "type", "") or "") != "SCRIPT":
                continue
            records.append(
                {
                    "window_index": window_index,
                    "screen": _name(screen),
                    "workspace": _name(workspace),
                    "area_index": area_index,
                    "type": "SCRIPT",
                    "region_count": len(_items(getattr(area, "regions", []))),
                }
            )
    return records


def _operator(ctx: Ctx, name: str) -> Any | None:
    script_ops = getattr(getattr(ctx.bpy, "ops", None), "script", None)
    return getattr(script_ops, name, None)


def _operator_status(ctx: Ctx, name: str) -> dict[str, Any]:
    op = _operator(ctx, name)
    if op is None:
        return {"available": False, "reason": f"operator not found: script.{name}"}
    poll = getattr(op, "poll", None)
    try:
        available = bool(poll()) if callable(poll) else True
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    if not available:
        return {"available": False, "reason": "operator poll returned false"}
    return {"available": True}


def _call_operator(ctx: Ctx, name: str, **kwargs: Any) -> Any:
    op = _operator(ctx, name)
    if op is None:
        raise BridgeError(PRECONDITION, f"operator not found: script.{name}")
    status = _operator_status(ctx, name)
    if not status["available"]:
        raise BridgeError(PRECONDITION, status.get("reason", f"script.{name} is unavailable"))
    return op(**kwargs)


def _require_python(ctx: Ctx) -> None:
    if not ctx.allow_python:
        raise BridgeError(
            PYTHON_DISABLED,
            "script execution is disabled; enable it explicitly for a trusted local session",
        )


def _require_path(payload: dict) -> str:
    raw = payload.get("path")
    if not isinstance(raw, str) or not raw:
        raise BridgeError(INVALID_PARAMS, "path is required")
    path = os.path.abspath(os.path.expanduser(raw))
    if not os.path.exists(path):
        raise BridgeError(INVALID_PARAMS, f"path does not exist: {raw}")
    return path


def _safe_call(fn: Any, default: Any) -> Any:
    if not callable(fn):
        return default
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def paths(ctx: Ctx, payload: dict) -> dict:
    utils = getattr(ctx.bpy, "utils", None)
    return {
        "script_path_user": _safe_call(getattr(utils, "script_path_user", None), None),
        "script_paths": _safe_call(getattr(utils, "script_paths", None), []),
        "script_paths_pref": _safe_call(getattr(utils, "script_paths_pref", None), []),
        "script_directories": _script_directories(ctx),
    }


def report(ctx: Ctx, payload: dict) -> dict:
    spaces = _spaces(ctx)
    path_info = paths(ctx, payload)
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "version_string": str(getattr(getattr(ctx.bpy, "app", None), "version_string", "") or ""),
        "area_count": len(spaces),
        "spaces": spaces,
        "preferences": _preferences(ctx),
        "paths": path_info,
        "operators": {name: _operator_status(ctx, name) for name in _SCRIPT_OPERATORS},
        "execution": {
            "allow_python": bool(ctx.allow_python),
            "run_file_gated": True,
            "reload_gated": True,
        },
    }


def run_file(ctx: Ctx, payload: dict) -> dict:
    _require_python(ctx)
    path = _require_path(payload)
    result = _call_operator(ctx, "python_file_run", filepath=path)
    if isinstance(result, set) and "CANCELLED" in result:
        raise BridgeError(PRECONDITION, f"script.python_file_run cancelled for {path}")
    return {
        "path": path,
        "applied": ["script.python_file_run"],
        "result": _json_value(result),
    }


def reload(ctx: Ctx, payload: dict) -> dict:
    _require_python(ctx)
    result = _call_operator(ctx, "reload")
    if isinstance(result, set) and "CANCELLED" in result:
        raise BridgeError(PRECONDITION, "script.reload cancelled")
    return {"applied": ["script.reload"], "result": _json_value(result)}


COMMANDS = [
    Command("script.report", report, mutates=False),
    Command("script.paths", paths, mutates=False),
    Command("script.run_file", run_file, mutates=True, feedback="viewport"),
    Command("script.reload", reload, mutates=True, feedback="viewport"),
]
