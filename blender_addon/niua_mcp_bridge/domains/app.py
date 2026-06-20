"""App/session/file lifecycle handlers."""

from __future__ import annotations

import os
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


def _state(ctx: Ctx) -> dict[str, Any]:
    bpy = ctx.bpy
    data = getattr(bpy, "data", None)
    scene = getattr(getattr(bpy, "context", None), "scene", None)
    workspace = _current_workspace(ctx)
    render = getattr(scene, "render", None)
    filepath = str(getattr(data, "filepath", "") or "")
    return {
        "version_string": str(getattr(getattr(bpy, "app", None), "version_string", "")),
        "version": list(getattr(getattr(bpy, "app", None), "version", []) or []),
        "background": bool(getattr(getattr(bpy, "app", None), "background", False)),
        "filepath": filepath,
        "is_saved": bool(filepath),
        "is_dirty": bool(getattr(data, "is_dirty", False)),
        "scene": getattr(scene, "name", None),
        "workspace": getattr(workspace, "name", None),
        "render_engine": getattr(render, "engine", None),
    }


def _dirty(ctx: Ctx) -> bool:
    return bool(getattr(getattr(ctx.bpy, "data", None), "is_dirty", False))


def _require_clean_or_force(ctx: Ctx, payload: dict, action: str) -> None:
    if _dirty(ctx) and not bool(payload.get("force", False)):
        raise BridgeError(PRECONDITION, f"{action} would discard unsaved changes; pass force=true")


def _require_abs_path(payload: dict, key: str = "path") -> str:
    path = payload.get(key)
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, f"{key} is required")
    if not os.path.isabs(path):
        raise BridgeError(INVALID_PARAMS, f"{key} must be absolute", {key: path})
    return path


def _require_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BridgeError(INVALID_PARAMS, f"{key} is required")
    return value


def _current_workspace(ctx: Ctx):
    context = getattr(ctx.bpy, "context", None)
    window = getattr(context, "window", None)
    return getattr(window, "workspace", None) or getattr(context, "workspace", None)


def _workspace_summary(ctx: Ctx) -> dict:
    data = getattr(ctx.bpy, "data", None)
    workspaces = list(getattr(data, "workspaces", []) or [])
    active = _current_workspace(ctx)
    return {
        "active": getattr(active, "name", None),
        "workspaces": [getattr(workspace, "name", "") for workspace in workspaces],
    }


def _get_workspace(ctx: Ctx, name: str):
    workspaces = getattr(getattr(ctx.bpy, "data", None), "workspaces", None)
    workspace = None
    if workspaces is not None and hasattr(workspaces, "get"):
        workspace = workspaces.get(name)
    if workspace is None:
        for candidate in list(workspaces or []):
            if getattr(candidate, "name", None) == name:
                workspace = candidate
                break
    if workspace is None:
        raise BridgeError(NOT_FOUND, f"workspace not found: {name}", {"name": name})
    return workspace


def _addon_utils():
    import addon_utils

    return addon_utils


def _addon_modules() -> dict[str, Any]:
    modules: dict[str, Any] = {}
    for module in _addon_utils().modules():
        name = getattr(module, "__name__", "")
        if name:
            modules[name] = module
    return modules


def _addon_record(module: Any) -> dict[str, Any]:
    module_name = getattr(module, "__name__", "")
    bl_info = getattr(module, "bl_info", {}) or {}
    enabled, loaded = _addon_utils().check(module_name)
    version = bl_info.get("version", [])
    if isinstance(version, tuple):
        version = list(version)
    return {
        "module": module_name,
        "name": bl_info.get("name", module_name),
        "version": version,
        "category": bl_info.get("category", ""),
        "enabled": bool(enabled),
        "loaded": bool(loaded),
    }


def _addons_summary() -> dict:
    records = sorted((_addon_record(module) for module in _addon_modules().values()), key=lambda item: item["module"])
    return {
        "addons": records,
        "enabled": [record["module"] for record in records if record["enabled"]],
    }


def _require_addon_module(module_name: str):
    modules = _addon_modules()
    module = modules.get(module_name)
    if module is None:
        raise BridgeError(NOT_FOUND, f"add-on module not found: {module_name}", {"module": module_name})
    return module


def _scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _pref_fields(obj: Any, names: list[str]) -> dict[str, Any]:
    return {name: _scalar(getattr(obj, name, None)) for name in names}


def info(ctx: Ctx, payload: dict) -> dict:
    return _state(ctx)


def file_new(ctx: Ctx, payload: dict) -> dict:
    _require_clean_or_force(ctx, payload, "file_new")
    ctx.bpy.ops.wm.read_factory_settings(use_empty=True)
    return _state(ctx)


def file_open(ctx: Ctx, payload: dict) -> dict:
    path = _require_abs_path(payload)
    if not os.path.exists(path):
        raise BridgeError(NOT_FOUND, f"file not found: {path}", {"path": path})
    _require_clean_or_force(ctx, payload, "file_open")
    ctx.bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    return _state(ctx)


def file_save(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    if isinstance(path, str) and path:
        path = _require_abs_path(payload)
        ctx.bpy.ops.wm.save_as_mainfile(filepath=path)
    else:
        current = str(getattr(getattr(ctx.bpy, "data", None), "filepath", "") or "")
        if not current:
            raise BridgeError(INVALID_PARAMS, "path is required for an unsaved file")
        ctx.bpy.ops.wm.save_mainfile()
    return _state(ctx)


def file_save_as(ctx: Ctx, payload: dict) -> dict:
    path = _require_abs_path(payload)
    ctx.bpy.ops.wm.save_as_mainfile(filepath=path)
    return _state(ctx)


def file_save_copy(ctx: Ctx, payload: dict) -> dict:
    path = _require_abs_path(payload)
    ctx.bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return _state(ctx)


def file_revert(ctx: Ctx, payload: dict) -> dict:
    current = str(getattr(getattr(ctx.bpy, "data", None), "filepath", "") or "")
    if not current:
        raise BridgeError(PRECONDITION, "cannot revert an unsaved file")
    if not bool(payload.get("force", False)):
        raise BridgeError(PRECONDITION, "file_revert reloads from disk; pass force=true")
    ctx.bpy.ops.wm.revert_mainfile()
    return _state(ctx)


def undo(ctx: Ctx, payload: dict) -> dict:
    ctx.bpy.ops.ed.undo()
    return {"ok": True, "applied": ["ed.undo"]}


def redo(ctx: Ctx, payload: dict) -> dict:
    ctx.bpy.ops.ed.redo()
    return {"ok": True, "applied": ["ed.redo"]}


def workspaces(ctx: Ctx, payload: dict) -> dict:
    return _workspace_summary(ctx)


def workspace_set(ctx: Ctx, payload: dict) -> dict:
    name = _require_string(payload, "name")
    workspace = _get_workspace(ctx, name)
    window = getattr(getattr(ctx.bpy, "context", None), "window", None)
    if window is None:
        raise BridgeError(PRECONDITION, "active window is required to set workspace")
    window.workspace = workspace
    return _workspace_summary(ctx)


def addons(ctx: Ctx, payload: dict) -> dict:
    return _addons_summary()


def addon_enable(ctx: Ctx, payload: dict) -> dict:
    module_name = _require_string(payload, "module")
    _require_addon_module(module_name)
    ctx.bpy.ops.preferences.addon_enable(module=module_name)
    enabled, loaded = _addon_utils().check(module_name)
    return {"module": module_name, "enabled": bool(enabled), "loaded": bool(loaded)}


def addon_disable(ctx: Ctx, payload: dict) -> dict:
    module_name = _require_string(payload, "module")
    _require_addon_module(module_name)
    ctx.bpy.ops.preferences.addon_disable(module=module_name)
    enabled, loaded = _addon_utils().check(module_name)
    return {"module": module_name, "enabled": bool(enabled), "loaded": bool(loaded)}


def preferences_summary(ctx: Ctx, payload: dict) -> dict:
    prefs = getattr(getattr(ctx.bpy, "context", None), "preferences", None)
    return {
        "view": _pref_fields(getattr(prefs, "view", None), ["ui_scale", "show_tooltips"]),
        "edit": _pref_fields(getattr(prefs, "edit", None), ["use_global_undo", "undo_steps"]),
        "filepaths": _pref_fields(
            getattr(prefs, "filepaths", None),
            ["temporary_directory", "render_output_directory"],
        ),
        "system": _pref_fields(getattr(prefs, "system", None), ["memory_cache_limit"]),
    }


def preferences_save(ctx: Ctx, payload: dict) -> dict:
    ctx.bpy.ops.wm.save_userpref()
    return {"ok": True, "applied": ["wm.save_userpref"]}


COMMANDS = [
    Command("app.info", info, mutates=False),
    Command("app.file_new", file_new, mutates=False),
    Command("app.file_open", file_open, mutates=False),
    Command("app.file_save", file_save, mutates=False),
    Command("app.file_save_as", file_save_as, mutates=False),
    Command("app.file_save_copy", file_save_copy, mutates=False),
    Command("app.file_revert", file_revert, mutates=False),
    Command("app.undo", undo, mutates=False),
    Command("app.redo", redo, mutates=False),
    Command("app.workspaces", workspaces, mutates=False),
    Command("app.workspace_set", workspace_set, mutates=False),
    Command("app.addons", addons, mutates=False),
    Command("app.addon_enable", addon_enable, mutates=False),
    Command("app.addon_disable", addon_disable, mutates=False),
    Command("app.preferences_summary", preferences_summary, mutates=False),
    Command("app.preferences_save", preferences_save, mutates=False),
]
