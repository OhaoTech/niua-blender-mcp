"""Scene tree / Outliner handlers.

This domain mirrors Blender's logical Outliner state through data APIs. It does not
drive GUI Outliner operators; GUI click parity belongs to the later UI subsystem.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

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


def _is_scene_root(ctx: Ctx, collection: Any) -> bool:
    return any(getattr(scene, "collection", None) is collection for scene in _iter(getattr(ctx.bpy.data, "scenes", [])))


def _collection_parents(ctx: Ctx, child: Any) -> list[Any]:
    parents = []
    for collection in _all_collections(ctx):
        if child in _iter(getattr(collection, "children", [])):
            parents.append(collection)
    return parents


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


def _find_layer_collection(layer_collection: Any, collection_name: str):
    collection = getattr(layer_collection, "collection", None)
    if _name(collection) == collection_name or _name(layer_collection) == collection_name:
        return layer_collection
    for child in _iter(getattr(layer_collection, "children", [])):
        found = _find_layer_collection(child, collection_name)
        if found is not None:
            return found
    return None


def _require_str(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BridgeError(INVALID_PARAMS, f"{key} is required")
    return value


def _optional_str(payload: dict, key: str) -> str:
    value = payload.get(key, "")
    return value if isinstance(value, str) else ""


def _copy_matrix(value: Any) -> Any:
    copier = getattr(value, "copy", None)
    return copier() if callable(copier) else value


def _remove_child(parent: Any, child: Any) -> None:
    children = getattr(parent, "children", None)
    if isinstance(children, list) and child in children:
        children.remove(child)


def _add_child(parent: Any, child: Any) -> None:
    children = getattr(parent, "children", None)
    if isinstance(children, list) and child not in children:
        children.append(child)


def _require_any_flag(payload: dict, names: tuple[str, ...]) -> None:
    if not any(name in payload and payload.get(name) is not None for name in names):
        raise BridgeError(INVALID_PARAMS, f"at least one of {', '.join(names)} is required")


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


def _orphan_count(ctx: Ctx) -> int:
    return int(orphans(ctx, {})["count"])


def collection_create(ctx: Ctx, payload: dict) -> dict:
    name = _require_str(payload, "name")
    parent_name = _optional_str(payload, "parent")
    scene = getattr(ctx.bpy.context, "scene", None)
    parent = _find_collection(ctx, parent_name) if parent_name else getattr(scene, "collection", None)
    if parent is None:
        raise BridgeError(PRECONDITION, "active scene root collection is required")
    collection = ctx.bpy.data.collections.new(name)
    parent.children.link(collection)
    return {"collection": _collection_flags(collection), "parent": _name(parent)}


def collection_rename(ctx: Ctx, payload: dict) -> dict:
    collection = _find_collection(ctx, _require_str(payload, "collection"))
    collection.name = _require_str(payload, "name")
    return {"collection": _collection_flags(collection)}


def collection_delete(ctx: Ctx, payload: dict) -> dict:
    name = _require_str(payload, "collection")
    collection = _find_collection(ctx, name)
    if _is_scene_root(ctx, collection):
        raise BridgeError(PRECONDITION, "cannot delete a scene root collection")
    has_contents = bool(_iter(getattr(collection, "objects", [])) or _iter(getattr(collection, "children", [])))
    if has_contents and not bool(payload.get("force", False)):
        raise BridgeError(PRECONDITION, "collection is not empty; pass force=true")
    for parent in list(_collection_parents(ctx, collection)):
        parent.children.unlink(collection)
    ctx.bpy.data.collections.remove(collection)
    return {"collection": name, "deleted": True}


def object_link(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(_require_str(payload, "object"))
    collection = _find_collection(ctx, _require_str(payload, "collection"))
    if not _collection_contains(collection, obj):
        collection.objects.link(obj)
    return {"object": _object_summary(obj)}


def object_unlink(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(_require_str(payload, "object"))
    collection = _find_collection(ctx, _require_str(payload, "collection"))
    users = _iter(getattr(obj, "users_collection", []))
    if collection in users and len(users) <= 1 and not bool(payload.get("force", False)):
        raise BridgeError(PRECONDITION, "object is only linked to this collection; pass force=true")
    if _collection_contains(collection, obj):
        collection.objects.unlink(obj)
    return {"object": _object_summary(obj)}


def object_move(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(_require_str(payload, "object"))
    target = _find_collection(ctx, _require_str(payload, "collection"))
    if not _collection_contains(target, obj):
        target.objects.link(obj)
    for collection in list(_iter(getattr(obj, "users_collection", []))):
        if collection is not target and _collection_contains(collection, obj):
            collection.objects.unlink(obj)
    return {"object": _object_summary(obj)}


def parent_set(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(_require_str(payload, "object"))
    parent = ctx.get_object(_require_str(payload, "parent"))
    if obj is parent:
        raise BridgeError(PRECONDITION, "object cannot be parented to itself")
    keep_transform = bool(payload.get("keep_transform", True))
    world = _copy_matrix(getattr(obj, "matrix_world", None)) if keep_transform else None
    old_parent = getattr(obj, "parent", None)
    if old_parent is not None and old_parent is not parent:
        _remove_child(old_parent, obj)
    obj.parent = parent
    _add_child(parent, obj)
    if keep_transform:
        parent_world = getattr(parent, "matrix_world", None)
        inverted = getattr(parent_world, "inverted", None)
        if callable(inverted):
            obj.matrix_parent_inverse = inverted()
        if world is not None:
            obj.matrix_world = world
    return {"object": _object_summary(obj)}


def parent_clear(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(_require_str(payload, "object"))
    keep_transform = bool(payload.get("keep_transform", True))
    world = _copy_matrix(getattr(obj, "matrix_world", None)) if keep_transform else None
    old_parent = getattr(obj, "parent", None)
    if old_parent is not None:
        _remove_child(old_parent, obj)
    obj.parent = None
    obj.matrix_parent_inverse = None
    if keep_transform and world is not None:
        obj.matrix_world = world
    return {"object": _object_summary(obj)}


def visibility_set(ctx: Ctx, payload: dict) -> dict:
    _require_any_flag(payload, ("viewport", "render", "selectable"))
    obj = ctx.get_object(_require_str(payload, "object"))
    if payload.get("viewport") is not None:
        obj.hide_viewport = not bool(payload["viewport"])
    if payload.get("render") is not None:
        obj.hide_render = not bool(payload["render"])
    if payload.get("selectable") is not None:
        obj.hide_select = not bool(payload["selectable"])
    return {"object": _object_summary(obj)}


def collection_visibility_set(ctx: Ctx, payload: dict) -> dict:
    _require_any_flag(payload, ("viewport", "render", "selectable"))
    collection = _find_collection(ctx, _require_str(payload, "collection"))
    if payload.get("viewport") is not None:
        collection.hide_viewport = not bool(payload["viewport"])
    if payload.get("render") is not None:
        collection.hide_render = not bool(payload["render"])
    if payload.get("selectable") is not None:
        collection.hide_select = not bool(payload["selectable"])
    return {"collection": _collection_flags(collection)}


def view_layers(ctx: Ctx, payload: dict) -> dict:
    scene = getattr(ctx.bpy.context, "scene", None)
    return {
        "view_layers": [
            _view_layer_summary(view_layer)
            for view_layer in _iter(getattr(scene, "view_layers", []))
        ]
    }


def view_layer_create(ctx: Ctx, payload: dict) -> dict:
    scene = getattr(ctx.bpy.context, "scene", None)
    name = _require_str(payload, "name")
    new = getattr(getattr(scene, "view_layers", None), "new", None)
    if not callable(new):
        raise BridgeError(PRECONDITION, "scene view layers cannot be created in this context")
    try:
        new(name=name)
    except TypeError:
        new(name)
    return view_layers(ctx, {})


def view_layer_delete(ctx: Ctx, payload: dict) -> dict:
    if not bool(payload.get("force", False)):
        raise BridgeError(PRECONDITION, "view_layer_delete changes render organization; pass force=true")
    scene = getattr(ctx.bpy.context, "scene", None)
    layers = getattr(scene, "view_layers", None)
    if len(_iter(layers)) <= 1:
        raise BridgeError(PRECONDITION, "cannot delete the last view layer")
    view_layer = _find_view_layer(ctx, _require_str(payload, "name"))
    remove = getattr(layers, "remove", None)
    if not callable(remove):
        raise BridgeError(PRECONDITION, "scene view layers cannot be removed in this context")
    remove(view_layer)
    return view_layers(ctx, {})


def layer_collection_set(ctx: Ctx, payload: dict) -> dict:
    _require_any_flag(payload, ("exclude", "viewport", "holdout", "indirect_only"))
    view_layer = _find_view_layer(ctx, _require_str(payload, "view_layer"))
    collection_name = _require_str(payload, "collection")
    _find_collection(ctx, collection_name)
    layer_collection = _find_layer_collection(getattr(view_layer, "layer_collection", None), collection_name)
    if layer_collection is None:
        raise BridgeError(
            NOT_FOUND,
            f"collection not found in view layer: {collection_name}",
            {"view_layer": _name(view_layer), "collection": collection_name},
        )
    if payload.get("exclude") is not None:
        layer_collection.exclude = bool(payload["exclude"])
    if payload.get("viewport") is not None:
        layer_collection.hide_viewport = not bool(payload["viewport"])
    if payload.get("holdout") is not None:
        layer_collection.holdout = bool(payload["holdout"])
    if payload.get("indirect_only") is not None:
        layer_collection.indirect_only = bool(payload["indirect_only"])
    return {"layer_collection": _layer_collection_summary(layer_collection)}


def orphans_purge(ctx: Ctx, payload: dict) -> dict:
    if not bool(payload.get("force", False)):
        raise BridgeError(PRECONDITION, "orphans_purge deletes datablocks; pass force=true")
    before = _orphan_count(ctx)
    purge = getattr(getattr(ctx.bpy, "data", None), "orphans_purge", None)
    removed: Any = None
    if callable(purge):
        try:
            removed = purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
        except TypeError:
            removed = purge()
    else:
        op = getattr(getattr(getattr(ctx.bpy, "ops", None), "outliner", None), "orphans_purge", None)
        if op is None:
            raise BridgeError(PRECONDITION, "orphan purge API is unavailable")
        op(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    after = _orphan_count(ctx)
    return {
        "purged": True,
        "before": before,
        "after": after,
        "removed": int(removed) if isinstance(removed, int) else max(before - after, 0),
    }


COMMANDS = [
    Command("outliner.tree", tree, mutates=False),
    Command("outliner.describe", describe, mutates=False),
    Command("outliner.find", find, mutates=False),
    Command("outliner.orphans", orphans, mutates=False),
    Command("outliner.collection_create", collection_create, mutates=True, feedback="viewport"),
    Command("outliner.collection_rename", collection_rename, mutates=True, feedback="viewport"),
    Command("outliner.collection_delete", collection_delete, mutates=True, feedback="viewport"),
    Command("outliner.object_link", object_link, mutates=True, feedback="viewport"),
    Command("outliner.object_unlink", object_unlink, mutates=True, feedback="viewport"),
    Command("outliner.object_move", object_move, mutates=True, feedback="viewport"),
    Command("outliner.parent_set", parent_set, mutates=True, feedback="viewport"),
    Command("outliner.parent_clear", parent_clear, mutates=True, feedback="viewport"),
    Command("outliner.visibility_set", visibility_set, mutates=True, feedback="viewport"),
    Command(
        "outliner.collection_visibility_set",
        collection_visibility_set,
        mutates=True,
        feedback="viewport",
    ),
    Command("outliner.view_layers", view_layers, mutates=False),
    Command("outliner.view_layer_create", view_layer_create, mutates=True, feedback="viewport"),
    Command("outliner.view_layer_delete", view_layer_delete, mutates=True, feedback="viewport"),
    Command("outliner.layer_collection_set", layer_collection_set, mutates=True, feedback="viewport"),
    Command("outliner.orphans_purge", orphans_purge, mutates=True, feedback="viewport"),
]
