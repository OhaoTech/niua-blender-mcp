"""Project editor GUI-parity handlers."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from ..context import Ctx
from ..dispatch import Command

_PROJECT_DIR = ".blender_project"
_PROJECT_CONFIG = "project.toml"
_PROJECT_OPERATORS = ("new_project", "save_project", "open_blend_in_project")


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
    try:
        return [_json_value(item) for item in value]
    except TypeError:
        return str(value)


def _spaces(ctx: Ctx) -> list[dict[str, Any]]:
    bpy_ctx = getattr(ctx.bpy, "context", None)
    wm = getattr(bpy_ctx, "window_manager", None)
    records: list[dict[str, Any]] = []
    for window_index, window in enumerate(_items(getattr(wm, "windows", []))):
        screen = getattr(window, "screen", None)
        workspace = getattr(window, "workspace", None) or getattr(bpy_ctx, "workspace", None)
        for area_index, area in enumerate(_items(getattr(screen, "areas", []))):
            if str(getattr(area, "type", "") or "") != "PROJECT":
                continue
            space = getattr(getattr(area, "spaces", None), "active", None)
            record: dict[str, Any] = {
                "window_index": window_index,
                "screen": _name(screen),
                "workspace": _name(workspace),
                "area_index": area_index,
                "type": "PROJECT",
                "region_count": len(_items(getattr(area, "regions", []))),
            }
            if space is not None:
                for prop in ("show_region_ui", "active_section"):
                    if hasattr(space, prop):
                        record[prop] = _json_value(getattr(space, prop))
            records.append(record)
    return records


def _operator_status(ctx: Ctx, name: str) -> dict[str, Any]:
    project_ops = getattr(getattr(ctx.bpy, "ops", None), "project", None)
    op = getattr(project_ops, name, None)
    if op is None:
        return {"available": False, "reason": f"operator not found: project.{name}"}
    poll = getattr(op, "poll", None)
    try:
        available = bool(poll()) if callable(poll) else True
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    if not available:
        return {"available": False, "reason": "operator poll returned false"}
    return {"available": True}


def _project_obj(ctx: Ctx) -> Any | None:
    return getattr(getattr(ctx.bpy, "data", None), "project", None)


def _project_summary(project: Any | None) -> dict[str, Any]:
    if project is None:
        return {
            "available": False,
            "reason": "bpy.data.project is not available or no project is loaded",
        }
    return {
        "available": True,
        "name": _name(project),
        "root_path": str(getattr(project, "root_path", "") or ""),
        "is_dirty": bool(getattr(project, "is_dirty", False)),
    }


def _filepath(ctx: Ctx) -> str:
    return str(getattr(getattr(ctx.bpy, "data", None), "filepath", "") or "")


def _detect_root_from_file(filepath: str) -> str | None:
    if not filepath:
        return None
    path = Path(filepath).expanduser()
    start = path if path.is_dir() else path.parent
    for parent in (start, *start.parents):
        if parent.joinpath(_PROJECT_DIR).is_dir():
            return str(parent)
    return None


def _root_path(ctx: Ctx) -> str | None:
    project = _project_obj(ctx)
    root = str(getattr(project, "root_path", "") or "") if project is not None else ""
    if root:
        return os.path.abspath(os.path.expanduser(root))
    detected = _detect_root_from_file(_filepath(ctx))
    return os.path.abspath(os.path.expanduser(detected)) if detected else None


def _config(root_path: str | None) -> dict[str, Any]:
    if not root_path:
        return {"path": None, "exists": False, "data": {}}
    path = Path(root_path).joinpath(_PROJECT_DIR, _PROJECT_CONFIG)
    out: dict[str, Any] = {"path": str(path), "exists": path.exists(), "data": {}}
    if not path.exists():
        return out
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return out
    out["data"] = data
    return out


def _preferences(ctx: Ctx) -> dict[str, Any]:
    prefs = getattr(getattr(ctx.bpy, "context", None), "preferences", None)
    return {
        "use_project_auto_save": bool(getattr(prefs, "use_project_auto_save", False)),
    }


def _list_blend_files(root_path: str | None, limit: int = 200) -> list[str]:
    if not root_path:
        return []
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        return []
    files: list[str] = []
    for path in sorted(root.rglob("*.blend")):
        try:
            files.append(str(path.relative_to(root)))
        except ValueError:
            files.append(str(path))
        if len(files) >= limit:
            break
    return files


def report(ctx: Ctx, payload: dict) -> dict:
    root = _root_path(ctx)
    spaces = _spaces(ctx)
    return {
        "background": bool(getattr(getattr(ctx.bpy, "app", None), "background", False)),
        "filepath": _filepath(ctx),
        "detected_root": root,
        "project": _project_summary(_project_obj(ctx)),
        "config": _config(root),
        "preferences": _preferences(ctx),
        "area_count": len(spaces),
        "spaces": spaces,
        "operators": {name: _operator_status(ctx, name) for name in _PROJECT_OPERATORS},
    }


def files(ctx: Ctx, payload: dict) -> dict:
    root = _root_path(ctx)
    config = _config(root)
    if not root:
        return {
            "available": False,
            "reason": "no active or detected Blender project",
            "root_path": None,
            "config": config,
            "blend_files": [],
            "project_files": [],
        }
    project_files = [str(Path(_PROJECT_DIR, _PROJECT_CONFIG))] if config["exists"] else []
    return {
        "available": True,
        "root_path": root,
        "config": config,
        "blend_files": _list_blend_files(root),
        "project_files": project_files,
    }


def settings(ctx: Ctx, payload: dict) -> dict:
    root = _root_path(ctx)
    return {
        "project": _project_summary(_project_obj(ctx)),
        "root_path": root,
        "config": _config(root),
        "preferences": _preferences(ctx),
    }


COMMANDS = [
    Command("project.report", report, mutates=False),
    Command("project.files", files, mutates=False),
    Command("project.settings", settings, mutates=False),
]
