"""Animation domain unit tests (fake-bpy).

Extends the FakeBpy pattern from tests/test_dispatch.py / test_mesh.py with the bits the
animation handlers need: a scene ``frame_current`` + ``frame_set``, object
``keyframe_insert`` / ``keyframe_delete`` methods that record calls and build f-curves,
an ``animation_data.action`` with f-curves + keyframe points, and ``bpy.data.actions``.
``bpy`` is injected into sys.modules so the lazily-imported context resolver runs against
the same fake.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import NOT_FOUND, PRECONDITION, BridgeError


class FakeKeyframePoint:
    def __init__(self, frame: float, value: float = 0.0, interpolation: str = "BEZIER") -> None:
        self.co = [float(frame), float(value)]
        self.interpolation = interpolation


class FakeFCurve:
    def __init__(self, data_path: str, index: int = 0, frames=()) -> None:
        self.data_path = data_path
        self.array_index = index
        self.keyframe_points = [
            FakeKeyframePoint(f[0], f[1]) if isinstance(f, tuple) else FakeKeyframePoint(f) for f in frames
        ]
        self.updated = False

    def update(self) -> None:
        self.updated = True


class FakeAction:
    def __init__(self, name: str, fcurves=None, frame_range=(1.0, 10.0)) -> None:
        self.name = name
        self.fcurves = list(fcurves or [])
        self.frame_range = frame_range


class FakeLayeredAction:
    def __init__(self, name: str, fcurves=None, frame_range=(1.0, 10.0)) -> None:
        self.name = name
        self.frame_range = frame_range
        self.slots = [object()]
        self.layers = [types.SimpleNamespace(strips=[FakeStrip(fcurves or [])])]


class FakeStrip:
    def __init__(self, fcurves) -> None:
        self._channelbag = types.SimpleNamespace(fcurves=list(fcurves))

    def channelbag(self, slot):
        return self._channelbag


class FakeAnimData:
    def __init__(self, action: FakeAction | None = None) -> None:
        self.action = action


class FakeObj:
    def __init__(self, name: str, type: str = "MESH", animation_data=None) -> None:
        self.name = name
        self.type = type
        self.animation_data = animation_data
        self._selected = False
        self.mode = "OBJECT"
        self.insert_calls: list = []
        self.delete_calls: list = []
        self.insert_ok = True
        self.delete_ok = True

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected

    def keyframe_insert(self, data_path: str, frame=0, index=-1, **kw):
        self.insert_calls.append((data_path, frame, index))
        if self.insert_ok and self.animation_data is None:
            # First key creates animation data + an f-curve, mirroring Blender.
            self.animation_data = FakeAnimData(
                FakeAction("Action", fcurves=[FakeFCurve(data_path, frames=[frame])])
            )
        return self.insert_ok

    def keyframe_delete(self, data_path: str, frame=0, index=-1, **kw):
        self.delete_calls.append((data_path, frame, index))
        return self.delete_ok


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.actions: list = []
        self._active_obj = None
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []
        self.frame_set_calls: list[int] = []

        bpy = self

        class _SceneNS:
            def __init__(self_inner):
                self_inner.objects = []
                self_inner.name = "Scene"
                self_inner.frame_current = 0
                self_inner.frame_start = 1
                self_inner.frame_end = 250
                self_inner.use_preview_range = False
                self_inner.frame_preview_start = 1
                self_inner.frame_preview_end = 250

            def frame_set(self_inner, frame, **kw):
                bpy.frame_set_calls.append(frame)
                self_inner.frame_current = frame

        self.scene = _SceneNS()
        self.render = types.SimpleNamespace(fps=24, fps_base=1.0)
        self.scene.render = self.render

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

            @active.setter
            def active(self_inner, value):
                bpy._active_obj = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        class _Context:
            scene = self.scene
            view_layer = self.view_layer

            @property
            def object(self_inner):
                return bpy._active_obj

            window_manager = types.SimpleNamespace(windows=[])

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()

        class _ObjectOps:
            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

            def undo(self_inner, **kw):
                pass

        self.ops = types.SimpleNamespace(object=_ObjectOps(), ed=_EdOps())

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        store = self.objects_by_name
        actions = self.actions

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))
            materials: dict = {}

        _Data.actions = actions
        return _Data()


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.delitem(sys.modules, "bmesh", raising=False)
    return Ctx(bpy), bpy


# -- set_frame ---------------------------------------------------------------------


def test_router_contains_animation_timeline_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"anim.timeline", "anim.set_timeline", "anim.keyframes"} <= names


def test_timeline_reports_scene_range(env) -> None:
    ctx, bpy = env
    bpy.scene.frame_current = 12
    bpy.scene.frame_start = 3
    bpy.scene.frame_end = 48
    bpy.scene.use_preview_range = True
    bpy.scene.frame_preview_start = 6
    bpy.scene.frame_preview_end = 18
    bpy.render.fps = 30
    bpy.render.fps_base = 1.001
    reg = build_default_registry()

    result = dispatch_on_main(reg, "anim.timeline", {}, ctx)

    assert result == {
        "scene": "Scene",
        "frame_current": 12,
        "frame_start": 3,
        "frame_end": 48,
        "use_preview_range": True,
        "frame_preview_start": 6,
        "frame_preview_end": 18,
        "fps": 30,
        "fps_base": 1.001,
    }
    assert bpy.undo_pushes == []


def test_set_timeline_updates_provided_fields(env) -> None:
    ctx, bpy = env
    bpy.scene.frame_start = 1
    bpy.scene.frame_end = 250
    bpy.render.fps = 24
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "anim.set_timeline",
        {"frame_start": 10, "frame_end": 120, "frame_current": 42, "fps": 60},
        ctx,
    )

    assert result["frame_start"] == 10
    assert result["frame_end"] == 120
    assert result["frame_current"] == 42
    assert result["fps"] == 60
    assert bpy.frame_set_calls == [42]
    assert bpy.undo_pushes == ["mcp:anim.set_timeline"]


def test_set_frame_sets_scene_frame_and_pushes_undo(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    result = dispatch_on_main(reg, "anim.set_frame", {"frame": 24}, ctx)
    assert result["frame"] == 24
    assert bpy.frame_set_calls == [24]
    assert bpy.scene.frame_current == 24
    assert bpy.undo_pushes == ["mcp:anim.set_frame"]


# -- insert_keyframe ---------------------------------------------------------------


def test_insert_keyframe_calls_object_method(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "anim.insert_keyframe", {"object": "Cube", "data_path": "location", "frame": 5}, ctx
    )
    assert result == {"object": "Cube", "data_path": "location", "frame": 5, "index": -1}
    cube = bpy.objects_by_name["Cube"]
    assert cube.insert_calls == [("location", 5, -1)]
    # Already in OBJECT mode, so the resolver issues no mode switch.
    assert bpy.mode_calls == []
    assert bpy.undo_pushes == ["mcp:anim.insert_keyframe"]


def test_insert_keyframe_defaults_to_current_frame(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    bpy.scene.frame_current = 12
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "anim.insert_keyframe", {"object": "Cube", "data_path": "location"}, ctx
    )
    assert result["frame"] == 12
    assert bpy.objects_by_name["Cube"].insert_calls == [("location", 12, -1)]


def test_insert_keyframe_passes_index(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(
        reg,
        "anim.insert_keyframe",
        {"object": "Cube", "data_path": "location", "frame": 1, "index": 2},
        ctx,
    )
    assert bpy.objects_by_name["Cube"].insert_calls == [("location", 1, 2)]


def test_insert_keyframe_failure_raises_precondition_no_undo(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.insert_ok = False
    bpy.add(obj)
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg, "anim.insert_keyframe", {"object": "Cube", "data_path": "nope"}, ctx
        )
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_insert_keyframe_defaults_to_active_object(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "anim.insert_keyframe", {"data_path": "location"}, ctx)
    assert result["object"] == "Cube"


# -- delete_keyframe ---------------------------------------------------------------


def test_delete_keyframe_calls_object_method(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "anim.delete_keyframe", {"object": "Cube", "data_path": "location", "frame": 5}, ctx
    )
    assert result["frame"] == 5
    assert bpy.objects_by_name["Cube"].delete_calls == [("location", 5, -1)]
    assert bpy.undo_pushes == ["mcp:anim.delete_keyframe"]


def test_delete_keyframe_missing_raises_precondition_no_undo(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.delete_ok = False
    bpy.add(obj)
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg, "anim.delete_keyframe", {"object": "Cube", "data_path": "location", "frame": 99}, ctx
        )
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


# -- set_interpolation -------------------------------------------------------------


def test_set_interpolation_rewrites_all_keyframe_points(env) -> None:
    ctx, bpy = env
    fc1 = FakeFCurve("location", index=0, frames=[1, 5, 10])
    fc2 = FakeFCurve("location", index=1, frames=[1, 10])
    obj = FakeObj("Cube", animation_data=FakeAnimData(FakeAction("Act", fcurves=[fc1, fc2])))
    bpy.add(obj)
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "anim.set_interpolation", {"object": "Cube", "interpolation": "LINEAR"}, ctx
    )
    assert result["fcurves"] == 2
    assert result["keyframes"] == 5
    assert all(p.interpolation == "LINEAR" for p in fc1.keyframe_points)
    assert all(p.interpolation == "LINEAR" for p in fc2.keyframe_points)
    assert fc1.updated and fc2.updated
    assert bpy.undo_pushes == ["mcp:anim.set_interpolation"]


def test_set_interpolation_no_fcurves_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))  # no animation_data
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg, "anim.set_interpolation", {"object": "Cube", "interpolation": "CONSTANT"}, ctx
        )
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


# -- list_actions (read-only) ------------------------------------------------------


def test_list_actions_reports_actions(env) -> None:
    ctx, bpy = env
    bpy.actions.append(
        FakeAction("Walk", fcurves=[FakeFCurve("location"), FakeFCurve("rotation_euler")], frame_range=(1.0, 24.0))
    )
    bpy.actions.append(FakeAction("Idle", fcurves=[], frame_range=(1.0, 1.0)))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "anim.list_actions", {}, ctx)
    assert result["count"] == 2
    assert result["actions"][0] == {"name": "Walk", "fcurves": 2, "frame_range": [1.0, 24.0]}
    assert bpy.undo_pushes == []  # read-only


def test_list_actions_counts_layered_action_fcurves(env) -> None:
    ctx, bpy = env
    bpy.actions.append(
        FakeLayeredAction(
            "Layered",
            fcurves=[FakeFCurve("location"), FakeFCurve("location", index=1)],
            frame_range=(1.0, 12.0),
        )
    )
    reg = build_default_registry()

    result = dispatch_on_main(reg, "anim.list_actions", {}, ctx)

    assert result["actions"] == [{"name": "Layered", "fcurves": 2, "frame_range": [1.0, 12.0]}]


# -- report (read-only) ------------------------------------------------------------


def test_report_counts_fcurves_and_keyframes(env) -> None:
    ctx, bpy = env
    fc1 = FakeFCurve("location", index=0, frames=[1, 5, 10])
    fc2 = FakeFCurve("location", index=1, frames=[1, 10])
    obj = FakeObj(
        "Cube",
        animation_data=FakeAnimData(FakeAction("Act", fcurves=[fc1, fc2], frame_range=(1.0, 10.0))),
    )
    bpy.add(obj)
    reg = build_default_registry()
    rep = dispatch_on_main(reg, "anim.report", {"object": "Cube"}, ctx)
    assert rep["object"] == "Cube"
    assert rep["action"] == "Act"
    assert rep["frame_range"] == [1.0, 10.0]
    assert rep["fcurves"] == 2
    assert rep["keyframes"] == 5
    assert bpy.undo_pushes == []


def test_report_object_without_animation(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    rep = dispatch_on_main(reg, "anim.report", {"object": "Cube"}, ctx)
    assert rep["action"] is None
    assert rep["frame_range"] is None
    assert rep["fcurves"] == 0
    assert rep["keyframes"] == 0


def test_keyframes_reports_fcurve_points(env) -> None:
    ctx, bpy = env
    fc1 = FakeFCurve("location", index=0, frames=[(1, 0.0), (10, 4.5)])
    fc1.keyframe_points[1].interpolation = "LINEAR"
    fc2 = FakeFCurve("rotation_euler", index=2, frames=[(5, 1.25)])
    obj = FakeObj(
        "Cube",
        animation_data=FakeAnimData(FakeAction("Act", fcurves=[fc1, fc2], frame_range=(1.0, 10.0))),
    )
    bpy.add(obj)
    reg = build_default_registry()

    result = dispatch_on_main(reg, "anim.keyframes", {"object": "Cube"}, ctx)

    assert result == {
        "object": "Cube",
        "action": "Act",
        "frame_range": [1.0, 10.0],
        "fcurve_count": 2,
        "keyframe_count": 3,
        "fcurves": [
            {
                "data_path": "location",
                "array_index": 0,
                "keyframes": [
                    {"frame": 1.0, "value": 0.0, "interpolation": "BEZIER"},
                    {"frame": 10.0, "value": 4.5, "interpolation": "LINEAR"},
                ],
            },
            {
                "data_path": "rotation_euler",
                "array_index": 2,
                "keyframes": [
                    {"frame": 5.0, "value": 1.25, "interpolation": "BEZIER"},
                ],
            },
        ],
    }
    assert bpy.undo_pushes == []


# -- precondition / not-found handling ---------------------------------------------


def test_missing_object_raises_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "anim.report", {"object": "Ghost"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_no_active_object_raises_precondition(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "anim.insert_keyframe", {"data_path": "location"}, ctx)
    assert exc.value.code == PRECONDITION
