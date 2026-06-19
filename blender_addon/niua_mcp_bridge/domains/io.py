"""IO domain handlers: import/export the asset files that bridge niua and Godot.

Decoupled by design: these handlers only ever touch *files*. ``io.import`` diffs the
scene's object set before/after the import to report exactly which objects the file
created (the same before/after pattern as ``scene.create_object``). Exports are
read-only w.r.t. the scene (``mutates=False``): they select the requested objects via
``ctx.ensure(select=...)`` only for the duration of the call and restore selection on
exit. ``io.prepare_godot`` is the one mutating export -- it applies transforms first.

Operator ids are verified against Blender 5.1.1; see the manifest for the table.
"""

from __future__ import annotations

import os
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

# -- format inference --------------------------------------------------------------

#: File extension (lowercase, no dot) -> canonical import/export format token.
EXT_TO_FORMAT: dict[str, str] = {
    "gltf": "GLTF",
    "glb": "GLB",
    "obj": "OBJ",
    "fbx": "FBX",
    "stl": "STL",
    "usd": "USD",
    "usda": "USD",
    "usdc": "USD",
    "usdz": "USD",
    "ply": "PLY",
    "dae": "DAE",
    "abc": "ABC",
}

#: format token -> (bpy.ops group, importer op). glTF and GLB share one importer.
IMPORTERS: dict[str, tuple[str, str]] = {
    "GLTF": ("import_scene", "gltf"),
    "GLB": ("import_scene", "gltf"),
    "OBJ": ("wm", "obj_import"),
    "FBX": ("import_scene", "fbx"),
    "STL": ("wm", "stl_import"),
    "USD": ("wm", "usd_import"),
    "PLY": ("wm", "ply_import"),
    "DAE": ("wm", "collada_import"),
    "ABC": ("wm", "alembic_import"),
}


def _infer_format(path: str) -> str:
    """Infer a format token from a file extension; clean precondition error if unknown."""
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    fmt = EXT_TO_FORMAT.get(ext)
    if fmt is None:
        raise BridgeError(
            PRECONDITION,
            f"cannot infer import format from extension: {ext or '(none)'}",
            {"path": path, "extension": ext},
        )
    return fmt


def _scene_names(ctx: Ctx) -> set[str]:
    scene = ctx.bpy.context.scene
    return {getattr(o, "name", "") for o in getattr(scene, "objects", []) or []}


# -- import ------------------------------------------------------------------------


def import_file(ctx: Ctx, payload: dict) -> dict:
    bpy = ctx.bpy
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required")
    if not os.path.exists(path):
        raise BridgeError(NOT_FOUND, f"file not found: {path}", {"path": path})

    fmt = str(payload.get("format", "AUTO")).upper()
    if fmt in ("", "AUTO"):
        fmt = _infer_format(path)
    if fmt not in IMPORTERS:
        raise BridgeError(
            PRECONDITION,
            f"unsupported import format: {fmt}",
            {"supported": sorted(IMPORTERS)},
        )

    group, op = IMPORTERS[fmt]
    importer = getattr(getattr(bpy.ops, group), op)

    before = _scene_names(ctx)
    importer(filepath=path)
    after = _scene_names(ctx)
    imported = [name for name in after if name not in before]

    return {"imported": imported, "path": path, "format": fmt}


# -- export helpers ----------------------------------------------------------------


def _resolve_objects(ctx: Ctx, raw: Any) -> list[Any]:
    """Resolve a comma-separated name string into object datablocks (NOT_FOUND on miss)."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return [ctx.get_object(n) for n in names]


def _scene_object_count(ctx: Ctx) -> int:
    return len(getattr(ctx.bpy.context.scene, "objects", []) or [])


def _export_gltf(ctx: Ctx, path: str, objects: list[Any], export_format: str,
                 apply_modifiers: bool, y_up: bool) -> int:
    """Run export_scene.gltf, selecting ``objects`` first when given. Returns object count."""
    bpy = ctx.bpy
    use_selection = bool(objects)
    op = bpy.ops.export_scene.gltf

    def _run() -> None:
        op(
            filepath=path,
            export_format=export_format,
            use_selection=use_selection,
            export_apply=apply_modifiers,
            export_yup=y_up,
        )

    if use_selection:
        active = objects[0]
        with ctx.ensure(active=active, mode="OBJECT", select=objects):
            _run()
        return len(objects)
    _run()
    return _scene_object_count(ctx)


def export_gltf(ctx: Ctx, payload: dict) -> dict:
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required")
    export_format = str(payload.get("format", "GLB")).upper()
    if export_format not in ("GLB", "GLTF_SEPARATE"):
        raise BridgeError(INVALID_PARAMS, f"unsupported glTF format: {export_format}")
    apply_modifiers = bool(payload.get("apply_modifiers", True))
    y_up = bool(payload.get("y_up", True))
    objects = _resolve_objects(ctx, payload.get("objects"))

    count = _export_gltf(ctx, path, objects, export_format, apply_modifiers, y_up)
    return {"path": path, "format": export_format, "object_count": count}


def _export_fbx(ctx: Ctx, path: str, objects: list[Any]) -> int:
    bpy = ctx.bpy
    use_selection = bool(objects)

    def _run() -> None:
        bpy.ops.export_scene.fbx(filepath=path, use_selection=use_selection)

    if use_selection:
        with ctx.ensure(active=objects[0], mode="OBJECT", select=objects):
            _run()
        return len(objects)
    _run()
    return _scene_object_count(ctx)


def _export_obj(ctx: Ctx, path: str, objects: list[Any]) -> int:
    bpy = ctx.bpy
    export_selected = bool(objects)

    def _run() -> None:
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=export_selected)

    if export_selected:
        with ctx.ensure(active=objects[0], mode="OBJECT", select=objects):
            _run()
        return len(objects)
    _run()
    return _scene_object_count(ctx)


def export(ctx: Ctx, payload: dict) -> dict:
    """Generic export: route to the right exporter for ``format``."""
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required")
    fmt = str(payload.get("format", "GLB")).upper()
    objects = _resolve_objects(ctx, payload.get("objects"))

    if fmt == "GLB":
        count = _export_gltf(ctx, path, objects, "GLB", True, True)
    elif fmt == "FBX":
        count = _export_fbx(ctx, path, objects)
    elif fmt == "OBJ":
        count = _export_obj(ctx, path, objects)
    else:
        raise BridgeError(
            INVALID_PARAMS,
            f"unsupported export format: {fmt}",
            {"supported": ["GLB", "FBX", "OBJ"]},
        )
    return {"path": path, "format": fmt, "object_count": count}


# -- prepare for Godot -------------------------------------------------------------


def prepare_godot(ctx: Ctx, payload: dict) -> dict:
    """Apply transforms on one object, then export just it to a Godot-ready GLB."""
    name = payload.get("object")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "object is required")
    path = payload.get("path")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required")

    obj = ctx.get_object(name)

    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(ctx.bpy.ops.object.transform_apply)
        ctx.bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        ctx.bpy.ops.export_scene.gltf(
            filepath=path,
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
        )

    return {"object": obj.name, "path": path, "applied": True}


COMMANDS = [
    Command("io.import", import_file, mutates=True, feedback="viewport"),
    Command("io.export_gltf", export_gltf, mutates=False),
    Command("io.export", export, mutates=False),
    Command("io.prepare_godot", prepare_godot, mutates=True, feedback="viewport"),
]
