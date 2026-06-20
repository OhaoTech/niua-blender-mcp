"""Scene tree / Outliner handlers.

This domain mirrors Blender's logical Outliner state through data APIs. It does not
drive GUI Outliner operators; GUI click parity belongs to the later UI subsystem.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, BridgeError

_ORPHAN_CATEGORIES = [
    "actions",
    "cameras",
    "collections",
    "curves",
    "images",
    "lights",
    "materials",
    "meshes",
    "objects",
]


def _name(item: Any) -> str:
    return str(getattr(item, "name", "") or "")


def _library_name(item: Any) -> str | None:
    library = getattr(item, "library", None)
    if library is None:
        return None
    return str(getattr(library, "filepath", None) or getattr(library, "name", "") or "")


def _iter(items: Any) -> list[Any]:
    try:
        return list(items or [])
    except TypeError:
        return []


def _collection_contains(collection: Any, obj: Any) -> bool:
    return obj in _iter(getattr(collection, "objects", []))


def _visible(obj: Any) -> bool:
    visible_get = getattr(obj, "visible_get", None)
    if callable(visible_get):
        try:
            return bool(visible_get())
        except TypeError:
            pass
    return not bool(getattr(obj, "hide_viewport", False))


def _object_summary(obj: Any) -> dict[str, Any]:
    parent = getattr(obj, "parent", None)
    children = [_name(child) for child in _iter(getattr(obj, "children", []))]
    collections = [_name(collection) for collection in _iter(getattr(obj, "users_collection", []))]
    return {
        "name": _name(obj),
        "type": str(getattr(obj, "type", "") or ""),
        "parent": _name(parent) if parent is not None else None,
        "children": children,
        "collections": collections,
        "visible": _visible(obj),
        "selectable": not bool(getattr(obj, "hide_select", False)),
        "renderable": not bool(getattr(obj, "hide_render", False)),
        "hide_viewport": bool(getattr(obj, "hide_viewport", False)),
        "hide_render": bool(getattr(obj, "hide_render", False)),
        "hide_select": bool(getattr(obj, "hide_select", False)),
        "users": int(getattr(obj, "users", 0) or 0),
        "library": _library_name(obj),
    }


def _collection_flags(collection: Any) -> dict[str, Any]:
    return {
        "name": _name(collection),
        "objects": [_name(obj) for obj in _iter(getattr(collection, "objects", []))],
        "children_names": [_name(child) for child in _iter(getattr(collection, "children", []))],
        "visible": not bool(getattr(collection, "hide_viewport", False)),
        "selectable": not bool(getattr(collection, "hide_select", False)),
        "renderable": not bool(getattr(collection, "hide_render", False)),
        "hide_viewport": bool(getattr(collection, "hide_viewport", False)),
        "hide_render": bool(getattr(collection, "hide_render", False)),
        "hide_select": bool(getattr(collection, "hide_select", False)),
        "color_tag": str(getattr(collection, "color_tag", "") or ""),
        "users": int(getattr(collection, "users", 0) or 0),
        "library": _library_name(collection),
    }


def _collection_summary(collection: Any) -> dict[str, Any]:
    out = _collection_flags(collection)
    out["objects"] = [_object_summary(obj) for obj in _iter(getattr(collection, "objects", []))]
    out["children"] = [_collection_summary(child) for child in _iter(getattr(collection, "children", []))]
    return out


def _layer_collection_summary(layer_collection: Any) -> dict[str, Any]:
    collection = getattr(layer_collection, "collection", None)
    return {
        "name": _name(layer_collection) or _name(collection),
        "collection": _name(collection),
        "exclude": bool(getattr(layer_collection, "exclude", False)),
        "hide_viewport": bool(getattr(layer_collection, "hide_viewport", False)),
        "holdout": bool(getattr(layer_collection, "holdout", False)),
        "indirect_only": bool(getattr(layer_collection, "indirect_only", False)),
        "children": [
            _layer_collection_summary(child)
            for child in _iter(getattr(layer_collection, "children", []))
        ],
    }


def _view_layer_summary(view_layer: Any) -> dict[str, Any]:
    layer_collection = getattr(view_layer, "layer_collection", None)
    active = getattr(view_layer, "active_layer_collection", None)
    return {
        "name": _name(view_layer),
        "active_layer_collection": _name(active) if active is not None else None,
        "layer_collection": _layer_collection_summary(layer_collection) if layer_collection else None,
    }


def _scene_summary(scene: Any) -> dict[str, Any]:
    root = getattr(scene, "collection", None)
    return {"name": _name(scene), "root_collection": _name(root) if root is not None else None}


def _walk_collections(collection: Any) -> Iterable[Any]:
    yield collection
    for child in _iter(getattr(collection, "children", [])):
        yield from _walk_collections(child)


def _all_collections(ctx: Ctx) -> list[Any]:
    seen: set[int] = set()
    out: list[Any] = []
    for scene in _iter(getattr(ctx.bpy.data, "scenes", [])):
        root = getattr(scene, "collection", None)
        if root is not None:
            for collection in _walk_collections(root):
                ident = id(collection)
                if ident not in seen:
                    seen.add(ident)
                    out.append(collection)
    for collection in _iter(getattr(ctx.bpy.data, "collections", [])):
        ident = id(collection)
        if ident not in seen:
            seen.add(ident)
            out.append(collection)
    return out


def _find_named(items: Any, name: str):
    getter = getattr(items, "get", None)
    if callable(getter):
        found = getter(name)
        if found is not None:
            return found
    for item in _iter(items):
        if _name(item) == name:
            return item
    return None


def _find_collection(ctx: Ctx, name: str):
    for collection in _all_collections(ctx):
        if _name(collection) == name:
            return collection
    raise BridgeError(NOT_FOUND, f"collection not found: {name}", {"collection": name})


def _find_scene(ctx: Ctx, name: str):
    scene = _find_named(getattr(ctx.bpy.data, "scenes", []), name)
    if scene is None:
        raise BridgeError(NOT_FOUND, f"scene not found: {name}", {"scene": name})
    return scene


def _find_view_layer(ctx: Ctx, name: str):
    scene = getattr(ctx.bpy.context, "scene", None)
    view_layer = _find_named(getattr(scene, "view_layers", []), name)
    if view_layer is None:
        raise BridgeError(NOT_FOUND, f"view layer not found: {name}", {"view_layer": name})
    return view_layer


def _require_str(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BridgeError(INVALID_PARAMS, f"{key} is required")
    return value


def tree(ctx: Ctx, payload: dict) -> dict:
    scene = getattr(ctx.bpy.context, "scene", None)
    root = getattr(scene, "collection", None)
    return {
        "scene": _name(scene),
        "scenes": [_name(item) for item in _iter(getattr(ctx.bpy.data, "scenes", []))],
        "view_layers": [
            _view_layer_summary(view_layer)
            for view_layer in _iter(getattr(scene, "view_layers", []))
        ],
        "root": _collection_summary(root) if root is not None else None,
    }


def describe(ctx: Ctx, payload: dict) -> dict:
    target = _require_str(payload, "target")
    kind = str(payload.get("kind", "AUTO") or "AUTO").upper()
    if kind == "AUTO":
        obj = getattr(ctx.bpy.data, "objects", None)
        found = _find_named(obj, target)
        if found is not None:
            return {"kind": "OBJECT", "object": _object_summary(found)}
        for resolver, out_kind, key, summary in (
            (_find_collection, "COLLECTION", "collection", _collection_flags),
            (_find_scene, "SCENE", "scene", _scene_summary),
            (_find_view_layer, "VIEW_LAYER", "view_layer", _view_layer_summary),
        ):
            try:
                item = resolver(ctx, target)
            except BridgeError:
                continue
            return {"kind": out_kind, key: summary(item)}
        raise BridgeError(NOT_FOUND, f"outliner target not found: {target}", {"target": target})
    if kind == "OBJECT":
        return {"kind": "OBJECT", "object": _object_summary(ctx.get_object(target))}
    if kind == "COLLECTION":
        return {"kind": "COLLECTION", "collection": _collection_flags(_find_collection(ctx, target))}
    if kind == "SCENE":
        return {"kind": "SCENE", "scene": _scene_summary(_find_scene(ctx, target))}
    if kind == "VIEW_LAYER":
        return {"kind": "VIEW_LAYER", "view_layer": _view_layer_summary(_find_view_layer(ctx, target))}
    raise BridgeError(INVALID_PARAMS, f"unsupported kind: {kind}")


def find(ctx: Ctx, payload: dict) -> dict:
    query = _require_str(payload, "query").lower()
    kind = str(payload.get("kind", "ANY") or "ANY").upper()
    limit = int(payload.get("limit", 50) or 50)
    matches: list[dict[str, Any]] = []

    def add(candidate_kind: str, name: str, **extra: Any) -> None:
        if kind not in {"ANY", "AUTO", candidate_kind}:
            return
        if query not in name.lower():
            return
        matches.append({"kind": candidate_kind, "name": name, **extra})

    for obj in _iter(getattr(ctx.bpy.data, "objects", [])):
        add("OBJECT", _name(obj), type=str(getattr(obj, "type", "") or ""))
    for collection in _all_collections(ctx):
        add("COLLECTION", _name(collection))
    for scene in _iter(getattr(ctx.bpy.data, "scenes", [])):
        add("SCENE", _name(scene))
    scene = getattr(ctx.bpy.context, "scene", None)
    for view_layer in _iter(getattr(scene, "view_layers", [])):
        add("VIEW_LAYER", _name(view_layer))

    matches.sort(key=lambda item: (item["kind"], item["name"]))
    return {"query": query, "matches": matches[:limit], "count": min(len(matches), limit)}


def orphans(ctx: Ctx, payload: dict) -> dict:
    grouped: dict[str, list[str]] = {}
    total = 0
    for category in _ORPHAN_CATEGORIES:
        items = [
            _name(item)
            for item in _iter(getattr(ctx.bpy.data, category, []))
            if int(getattr(item, "users", 0) or 0) == 0
        ]
        grouped[category] = sorted(name for name in items if name)
        total += len(grouped[category])
    return {"orphans": grouped, "count": total}


COMMANDS = [
    Command("outliner.tree", tree, mutates=False),
    Command("outliner.describe", describe, mutates=False),
    Command("outliner.find", find, mutates=False),
    Command("outliner.orphans", orphans, mutates=False),
]
