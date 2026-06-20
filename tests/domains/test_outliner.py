from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, PRECONDITION, BridgeError


class _NamedList(list):
    def get(self, name: str):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None

    def keys(self):
        return [item.name for item in self]


class _ObjectLinks(_NamedList):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def link(self, obj):
        if obj not in self:
            self.append(obj)
        if self.owner not in obj.users_collection:
            obj.users_collection.append(self.owner)

    def unlink(self, obj):
        if obj in self:
            self.remove(obj)
        if self.owner in obj.users_collection:
            obj.users_collection.remove(self.owner)


class _CollectionLinks(_NamedList):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def link(self, collection):
        if collection not in self:
            self.append(collection)
        if self.owner not in collection.parents:
            collection.parents.append(self.owner)

    def unlink(self, collection):
        if collection in self:
            self.remove(collection)
        if self.owner in collection.parents:
            collection.parents.remove(self.owner)


class _CollectionDatablocks(_NamedList):
    def new(self, name: str):
        collection = FakeCollection(name)
        self.append(collection)
        return collection

    def remove(self, collection):
        if collection in self:
            list.remove(self, collection)
        for parent in list(collection.parents):
            parent.children.unlink(collection)


class FakeMatrix:
    def __init__(self, label: str) -> None:
        self.label = label

    def copy(self):
        return FakeMatrix(self.label)

    def inverted(self):
        return FakeMatrix(f"{self.label}.inverted")

    def __eq__(self, other):
        return isinstance(other, FakeMatrix) and self.label == other.label

    def __repr__(self) -> str:
        return f"FakeMatrix({self.label!r})"


class FakeObject:
    def __init__(self, name: str, obj_type: str = "MESH") -> None:
        self.name = name
        self.type = obj_type
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.hide_viewport = False
        self.hide_render = False
        self.hide_select = False
        self.parent = None
        self.children = []
        self.users_collection = []
        self.library = None
        self.users = 1
        self.matrix_world = FakeMatrix(f"{name}.world")
        self.matrix_parent_inverse = None

    def visible_get(self):
        return not self.hide_viewport


class FakeCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.objects = _ObjectLinks(self)
        self.children = _CollectionLinks(self)
        self.parents = []
        self.hide_viewport = False
        self.hide_render = False
        self.hide_select = False
        self.color_tag = "NONE"
        self.library = None
        self.users = 1


class FakeLayerCollection:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.name = collection.name
        self.children = _NamedList()
        self.exclude = False
        self.hide_viewport = False
        self.holdout = False
        self.indirect_only = False


def _build_layer_collection(collection: FakeCollection) -> FakeLayerCollection:
    layer = FakeLayerCollection(collection)
    for child in collection.children:
        layer.children.append(_build_layer_collection(child))
    return layer


class FakeViewLayer:
    def __init__(self, name: str, layer_collection: FakeLayerCollection) -> None:
        self.name = name
        self.layer_collection = layer_collection
        self.active_layer_collection = layer_collection


class _ViewLayers(_NamedList):
    def __init__(self, root: FakeCollection) -> None:
        super().__init__([FakeViewLayer("ViewLayer", _build_layer_collection(root))])
        self.root = root

    def new(self, name: str):
        view_layer = FakeViewLayer(name, _build_layer_collection(self.root))
        self.append(view_layer)
        return view_layer

    def remove(self, view_layer):
        list.remove(self, view_layer)


class FakeScene:
    def __init__(self, root: FakeCollection, objects: _NamedList, view_layers: _NamedList) -> None:
        self.name = "Scene"
        self.collection = root
        self.objects = objects
        self.view_layers = view_layers


class FakeData:
    def __init__(self, scene: FakeScene, collections: _NamedList, objects: _NamedList) -> None:
        self.scenes = _NamedList([scene])
        self.collections = _CollectionDatablocks(collections)
        self.objects = objects
        self.meshes = _NamedList([types.SimpleNamespace(name="UnusedMesh", users=0)])
        self.materials = _NamedList([types.SimpleNamespace(name="UsedMat", users=1)])
        self.images = _NamedList()
        self.curves = _NamedList()
        self.cameras = _NamedList()
        self.lights = _NamedList()
        self.actions = _NamedList([types.SimpleNamespace(name="LooseAction", users=0)])
        self.orphans_purge_calls = []

    def orphans_purge(self, **kwargs):
        self.orphans_purge_calls.append(kwargs)
        removed = 0
        for category in ("meshes", "materials", "images", "curves", "cameras", "lights", "actions", "collections", "objects"):
            items = getattr(self, category)
            for item in list(items):
                if int(getattr(item, "users", 0) or 0) == 0:
                    items.remove(item)
                    removed += 1
        return removed


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        root = FakeCollection("Scene Collection")
        props = FakeCollection("Props")
        nested = FakeCollection("Nested")
        root.children.link(props)
        props.children.link(nested)

        rig = FakeObject("Rig", "EMPTY")
        cube = FakeObject("Cube", "MESH")
        cube.parent = rig
        rig.children.append(cube)
        root.objects.link(rig)
        props.objects.link(cube)
        objects = _NamedList([rig, cube])

        view_layers = _ViewLayers(root)

        scene = FakeScene(root, objects, view_layers)
        self.data = FakeData(scene, _NamedList([props, nested]), objects)
        self.context = types.SimpleNamespace(scene=scene, view_layer=view_layers[0])
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="", **kw: None))


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_tree_returns_scene_collection_object_and_view_layer_state(env):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "outliner.tree", {}, ctx)

    assert out["scene"] == "Scene"
    assert out["scenes"] == ["Scene"]
    assert out["view_layers"][0]["name"] == "ViewLayer"
    root = out["root"]
    assert root["name"] == "Scene Collection"
    assert root["children"][0]["name"] == "Props"
    assert root["children"][0]["children"][0]["name"] == "Nested"
    rig = next(obj for obj in root["objects"] if obj["name"] == "Rig")
    cube = root["children"][0]["objects"][0]
    assert rig["children"] == ["Cube"]
    assert cube["name"] == "Cube"
    assert cube["parent"] == "Rig"
    assert cube["collections"] == ["Props"]
    assert cube["visible"] is True
    assert cube["selectable"] is True
    assert cube["renderable"] is True


def test_describe_resolves_object_collection_scene_and_view_layer(env):
    ctx, _bpy = env
    reg = build_default_registry()

    obj = dispatch_on_main(reg, "outliner.describe", {"target": "Cube"}, ctx)
    collection = dispatch_on_main(
        reg, "outliner.describe", {"target": "Props", "kind": "COLLECTION"}, ctx
    )
    scene = dispatch_on_main(reg, "outliner.describe", {"target": "Scene", "kind": "SCENE"}, ctx)
    view_layer = dispatch_on_main(
        reg, "outliner.describe", {"target": "ViewLayer", "kind": "VIEW_LAYER"}, ctx
    )

    assert obj["kind"] == "OBJECT"
    assert obj["object"]["parent"] == "Rig"
    assert collection["kind"] == "COLLECTION"
    assert collection["collection"]["objects"] == ["Cube"]
    assert scene == {"kind": "SCENE", "scene": {"name": "Scene", "root_collection": "Scene Collection"}}
    assert view_layer["kind"] == "VIEW_LAYER"
    assert view_layer["view_layer"]["name"] == "ViewLayer"


def test_find_searches_supported_outliner_kinds(env):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "outliner.find", {"query": "e", "limit": 10}, ctx)

    names = {(match["kind"], match["name"]) for match in out["matches"]}
    assert ("OBJECT", "Cube") in names
    assert ("COLLECTION", "Nested") in names
    assert ("SCENE", "Scene") in names
    assert ("VIEW_LAYER", "ViewLayer") in names


def test_orphans_lists_zero_user_datablocks(env):
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "outliner.orphans", {}, ctx)

    assert out["orphans"] == {
        "actions": ["LooseAction"],
        "cameras": [],
        "collections": [],
        "curves": [],
        "images": [],
        "lights": [],
        "materials": [],
        "meshes": ["UnusedMesh"],
        "objects": [],
    }
    assert out["count"] == 2


def test_collection_create_rename_and_delete_guards(env):
    ctx, bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(reg, "outliner.collection_create", {"name": "Shots"}, ctx)
    assert created["collection"]["name"] == "Shots"
    assert [child.name for child in bpy.context.scene.collection.children][-1] == "Shots"

    sub = dispatch_on_main(
        reg, "outliner.collection_create", {"name": "Shot010", "parent": "Shots"}, ctx
    )
    assert sub["collection"]["name"] == "Shot010"
    assert bpy.data.collections.get("Shots").children.get("Shot010") is not None

    renamed = dispatch_on_main(
        reg, "outliner.collection_rename", {"collection": "Shot010", "name": "Shot020"}, ctx
    )
    assert renamed["collection"]["name"] == "Shot020"
    assert bpy.data.collections.get("Shot020") is not None

    deleted = dispatch_on_main(reg, "outliner.collection_delete", {"collection": "Shot020"}, ctx)
    assert deleted == {"collection": "Shot020", "deleted": True}
    assert bpy.data.collections.get("Shot020") is None

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "outliner.collection_delete", {"collection": "Props"}, ctx)
    assert exc.value.code == PRECONDITION

    forced = dispatch_on_main(
        reg, "outliner.collection_delete", {"collection": "Props", "force": True}, ctx
    )
    assert forced == {"collection": "Props", "deleted": True}
    assert bpy.data.collections.get("Props") is None


def test_object_link_unlink_and_move_use_actual_collection_membership(env):
    ctx, bpy = env
    reg = build_default_registry()

    linked = dispatch_on_main(reg, "outliner.object_link", {"object": "Cube", "collection": "Nested"}, ctx)
    assert linked["object"]["collections"] == ["Props", "Nested"]
    assert bpy.data.collections.get("Nested").objects.get("Cube") is not None

    unlinked = dispatch_on_main(
        reg, "outliner.object_unlink", {"object": "Cube", "collection": "Props"}, ctx
    )
    assert unlinked["object"]["collections"] == ["Nested"]
    assert bpy.data.collections.get("Props").objects.get("Cube") is None

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "outliner.object_unlink", {"object": "Cube", "collection": "Nested"}, ctx)
    assert exc.value.code == PRECONDITION

    moved = dispatch_on_main(reg, "outliner.object_move", {"object": "Rig", "collection": "Props"}, ctx)
    assert moved["object"]["collections"] == ["Props"]
    assert bpy.context.scene.collection.objects.get("Rig") is None
    assert bpy.data.collections.get("Props").objects.get("Rig") is not None


def test_parent_set_and_clear_preserve_world_transform_and_reject_self_parent(env):
    ctx, bpy = env
    reg = build_default_registry()
    cube = bpy.data.objects.get("Cube")
    rig = bpy.data.objects.get("Rig")

    cleared = dispatch_on_main(reg, "outliner.parent_clear", {"object": "Cube"}, ctx)
    assert cleared["object"]["parent"] is None
    assert cube.parent is None
    assert cube.matrix_world == FakeMatrix("Cube.world")

    parented = dispatch_on_main(
        reg, "outliner.parent_set", {"object": "Cube", "parent": "Rig"}, ctx
    )
    assert parented["object"]["parent"] == "Rig"
    assert cube.parent is rig
    assert cube.matrix_parent_inverse == FakeMatrix("Rig.world.inverted")
    assert cube.matrix_world == FakeMatrix("Cube.world")

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "outliner.parent_set", {"object": "Cube", "parent": "Cube"}, ctx)
    assert exc.value.code == PRECONDITION


def test_visibility_set_maps_to_object_hide_flags(env):
    ctx, bpy = env
    reg = build_default_registry()
    cube = bpy.data.objects.get("Cube")

    out = dispatch_on_main(
        reg,
        "outliner.visibility_set",
        {"object": "Cube", "viewport": False, "render": False, "selectable": False},
        ctx,
    )
    assert cube.hide_viewport is True
    assert cube.hide_render is True
    assert cube.hide_select is True
    assert out["object"]["visible"] is False
    assert out["object"]["renderable"] is False
    assert out["object"]["selectable"] is False

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "outliner.visibility_set", {"object": "Cube"}, ctx)
    assert exc.value.code == INVALID_PARAMS


def test_collection_visibility_set_maps_to_collection_hide_flags(env):
    ctx, bpy = env
    reg = build_default_registry()
    props = bpy.data.collections.get("Props")

    out = dispatch_on_main(
        reg,
        "outliner.collection_visibility_set",
        {"collection": "Props", "viewport": False, "render": False, "selectable": False},
        ctx,
    )
    assert props.hide_viewport is True
    assert props.hide_render is True
    assert props.hide_select is True
    assert out["collection"]["visible"] is False
    assert out["collection"]["renderable"] is False
    assert out["collection"]["selectable"] is False

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "outliner.collection_visibility_set", {"collection": "Props"}, ctx)
    assert exc.value.code == INVALID_PARAMS


def test_view_layers_create_delete_and_guard_last_layer(env):
    ctx, bpy = env
    reg = build_default_registry()

    listed = dispatch_on_main(reg, "outliner.view_layers", {}, ctx)
    assert [layer["name"] for layer in listed["view_layers"]] == ["ViewLayer"]

    created = dispatch_on_main(reg, "outliner.view_layer_create", {"name": "Beauty"}, ctx)
    assert [layer["name"] for layer in created["view_layers"]] == ["ViewLayer", "Beauty"]

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "outliner.view_layer_delete", {"name": "Beauty"}, ctx)
    assert exc.value.code == PRECONDITION

    deleted = dispatch_on_main(
        reg, "outliner.view_layer_delete", {"name": "Beauty", "force": True}, ctx
    )
    assert [layer["name"] for layer in deleted["view_layers"]] == ["ViewLayer"]
    assert bpy.context.scene.view_layers.get("Beauty") is None

    with pytest.raises(BridgeError) as exc2:
        dispatch_on_main(
            reg, "outliner.view_layer_delete", {"name": "ViewLayer", "force": True}, ctx
        )
    assert exc2.value.code == PRECONDITION


def test_layer_collection_set_maps_restriction_flags(env):
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "outliner.layer_collection_set",
        {
            "view_layer": "ViewLayer",
            "collection": "Props",
            "exclude": True,
            "viewport": False,
            "holdout": True,
            "indirect_only": True,
        },
        ctx,
    )
    props_layer = bpy.context.scene.view_layers.get("ViewLayer").layer_collection.children.get("Props")
    assert props_layer.exclude is True
    assert props_layer.hide_viewport is True
    assert props_layer.holdout is True
    assert props_layer.indirect_only is True
    assert out["layer_collection"]["collection"] == "Props"

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "outliner.layer_collection_set",
            {"view_layer": "ViewLayer", "collection": "Props"},
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS


def test_orphans_purge_requires_force_and_uses_data_api(env):
    ctx, bpy = env
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "outliner.orphans_purge", {}, ctx)
    assert exc.value.code == PRECONDITION

    out = dispatch_on_main(reg, "outliner.orphans_purge", {"force": True}, ctx)
    assert out == {"purged": True, "before": 2, "after": 0, "removed": 2}
    assert bpy.data.orphans_purge_calls == [
        {"do_local_ids": True, "do_linked_ids": False, "do_recursive": True}
    ]
