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
    workspace = getattr(getattr(bpy, "context", None), "workspace", None)
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


COMMANDS = [
    Command("app.info", info, mutates=False),
    Command("app.file_new", file_new, mutates=False),
    Command("app.file_open", file_open, mutates=False),
    Command("app.file_save", file_save, mutates=False),
    Command("app.file_save_as", file_save_as, mutates=False),
    Command("app.file_save_copy", file_save_copy, mutates=False),
    Command("app.file_revert", file_revert, mutates=False),
]
