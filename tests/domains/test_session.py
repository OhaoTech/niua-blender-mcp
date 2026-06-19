"""Session domain unit tests (fake-bpy).

Checkpoint snapshots ``obj.data.copy()`` (a marker datablock) + transform into the store
without touching the visible scene (mutates=False, no undo push); revert swaps a *fresh*
copy of the stored datablock back onto the object and restores the transform (mutates=True,
one undo push); list reflects what's stored; reverting an object with no checkpoint is a
clean ``not_found``. The snapshot store is reset between tests for isolation.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.core import session as store
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import NOT_FOUND, PRECONDITION, BridgeError


class FakeMeshData:
    """A datablock whose ``copy()`` returns a fresh distinct marker, like bpy.types.Mesh."""

    _counter = 0

    def __init__(self, tag: str, verts: int = 0, polys: int = 0) -> None:
        self.tag = tag
        self.vertices = [object() for _ in range(verts)]
        self.polygons = [object() for _ in range(polys)]

    def copy(self) -> "FakeMeshData":
        FakeMeshData._counter += 1
        clone = FakeMeshData(self.tag, len(self.vertices), len(self.polygons))
        clone.origin = self.tag
        clone.copy_id = FakeMeshData._counter
        return clone


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.data = FakeMeshData("orig", verts=8, polys=6)
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.matrix_world = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self._active_obj = None
        self.undo_pushes: list[str] = []
        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        class _Context:
            view_layer = self.view_layer

            @property
            def object(self_inner):
                return bpy._active_obj

        self.context = _Context()

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(ed=_EdOps())

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects_by_name[obj.name] = obj
        self._active_obj = obj
        return obj

    @property
    def data(self):
        store_ = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store_.get(name))

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    store.reset()
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


# -- checkpoint --------------------------------------------------------------------


def test_checkpoint_stores_a_data_copy_without_mutating(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    original_data = obj.data
    reg = build_default_registry()
    out = dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "base"}, ctx)
    assert out == {"object": "Cube", "label": "base"}
    # The object's live data is untouched, and the stored snapshot is a *copy* (not the live one).
    assert obj.data is original_data
    snap = store.get_snapshot("Cube", "base")
    assert snap["data"] is not original_data
    assert snap["data"].origin == "orig"
    # checkpoint is read-only: no undo step pushed.
    assert bpy.undo_pushes == []


def test_checkpoint_auto_labels_when_omitted(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    out = dispatch_on_main(reg, "session.checkpoint", {"object": "Cube"}, ctx)
    assert out["object"] == "Cube"
    assert isinstance(out["label"], str) and out["label"]


def test_checkpoint_defaults_to_active_object(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))  # becomes active
    reg = build_default_registry()
    out = dispatch_on_main(reg, "session.checkpoint", {}, ctx)
    assert out["object"] == "Cube"


# -- revert ------------------------------------------------------------------------


def test_revert_swaps_a_fresh_copy_back_and_restores_transform(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "base"}, ctx)

    # Simulate an edit that worsened the model.
    obj.data = FakeMeshData("edited", verts=99, polys=99)
    obj.location = [5.0, 0.0, 0.0]
    stored = store.get_snapshot("Cube", "base")["data"]

    out = dispatch_on_main(reg, "session.revert", {"object": "Cube", "label": "base"}, ctx)
    assert out["object"] == "Cube"
    assert out["label"] == "base"
    assert out["vertices"] == 8 and out["faces"] == 6  # back to the snapshot's counts
    # A *fresh* copy was swapped in: it carries the snapshot's origin but is not the stored
    # datablock itself, so the snapshot survives for a repeat revert.
    assert obj.data.origin == "orig"
    assert obj.data is not stored
    assert obj.location == [0.0, 0.0, 0.0]
    # revert mutates -> exactly one undo step.
    assert bpy.undo_pushes == ["niua:session.revert"]


def test_revert_can_be_repeated_from_the_same_checkpoint(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "base"}, ctx)
    obj.data = FakeMeshData("edit1", verts=1, polys=1)
    dispatch_on_main(reg, "session.revert", {"object": "Cube"}, ctx)
    assert obj.data.origin == "orig"
    obj.data = FakeMeshData("edit2", verts=2, polys=2)
    out = dispatch_on_main(reg, "session.revert", {"object": "Cube"}, ctx)
    assert obj.data.origin == "orig"
    assert out["vertices"] == 8


def test_revert_most_recent_when_no_label(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    obj.data = FakeMeshData("a", verts=1, polys=1)
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "first"}, ctx)
    obj.data = FakeMeshData("b", verts=2, polys=2)
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "second"}, ctx)
    obj.data = FakeMeshData("c", verts=3, polys=3)
    out = dispatch_on_main(reg, "session.revert", {"object": "Cube"}, ctx)
    assert out["label"] == "second"  # most recent
    assert out["vertices"] == 2


def test_revert_without_checkpoint_is_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "session.revert", {"object": "Cube"}, ctx)
    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []  # nothing mutated


def test_revert_missing_label_is_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "base"}, ctx)
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "session.revert", {"object": "Cube", "label": "ghost"}, ctx)
    assert exc.value.code == NOT_FOUND


# -- list --------------------------------------------------------------------------


def test_list_checkpoints_reflects_store(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "a"}, ctx)
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "b"}, ctx)
    out = dispatch_on_main(reg, "session.list_checkpoints", {"object": "Cube"}, ctx)
    labels = [c["label"] for c in out["checkpoints"]]
    assert labels == ["a", "b"]  # oldest first
    assert all(c["object"] == "Cube" for c in out["checkpoints"])
    # read-only
    assert bpy.undo_pushes == []


def test_list_checkpoints_all_objects(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    bpy.add(FakeObj("Sphere"))
    reg = build_default_registry()
    dispatch_on_main(reg, "session.checkpoint", {"object": "Cube", "label": "a"}, ctx)
    dispatch_on_main(reg, "session.checkpoint", {"object": "Sphere", "label": "b"}, ctx)
    out = dispatch_on_main(reg, "session.list_checkpoints", {}, ctx)
    objs = {c["object"] for c in out["checkpoints"]}
    assert objs == {"Cube", "Sphere"}


def test_list_checkpoints_empty(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    out = dispatch_on_main(reg, "session.list_checkpoints", {"object": "Cube"}, ctx)
    assert out["checkpoints"] == []


# -- no active object --------------------------------------------------------------


def test_checkpoint_no_active_object_is_precondition(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "session.checkpoint", {}, ctx)
    assert exc.value.code == PRECONDITION
