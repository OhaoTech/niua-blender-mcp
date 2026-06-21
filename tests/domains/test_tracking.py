"""Tracking / Clip Editor GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, BridgeError


class FakeRnaProp:
    def __init__(self, identifier: str, type: str, *, is_readonly: bool = False) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = False
        self.array_length = 0
        self.enum_items = []
        self.enum_items_static = []


class FakeRnaProperties(list):
    def get(self, identifier: str):
        return next((prop for prop in self if prop.identifier == identifier), None)

    def __getitem__(self, key):
        if isinstance(key, str):
            prop = self.get(key)
            if prop is None:
                raise KeyError(key)
            return prop
        return super().__getitem__(key)


def _rna(*props: FakeRnaProp):
    return types.SimpleNamespace(properties=FakeRnaProperties([FakeRnaProp("rna_type", "POINTER", is_readonly=True), *props]))


class FakeMarker:
    def __init__(self, frame: int, co: list[float]) -> None:
        self.frame = frame
        self.co = co
        self.mute = False
        self.pattern_corners = [[-0.1, -0.1], [0.1, -0.1], [0.1, 0.1], [-0.1, 0.1]]
        self.search_min = [-0.25, -0.25]
        self.search_max = [0.25, 0.25]
        self.bl_rna = _rna(
            FakeRnaProp("frame", "INT", is_readonly=True),
            FakeRnaProp("co", "FLOAT"),
            FakeRnaProp("mute", "BOOLEAN"),
            FakeRnaProp("pattern_corners", "FLOAT"),
            FakeRnaProp("search_min", "FLOAT"),
            FakeRnaProp("search_max", "FLOAT"),
        )


class FakeTrack:
    def __init__(self, name: str = "Tracker") -> None:
        self.name = name
        self.select = True
        self.lock = False
        self.mute = False
        self.hide = False
        self.use_custom_color = False
        self.color = [1.0, 0.0, 0.0]
        self.average_error = 0.25
        self.markers = [FakeMarker(1, [0.1, 0.2]), FakeMarker(2, [0.2, 0.3])]
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("select", "BOOLEAN"),
            FakeRnaProp("lock", "BOOLEAN"),
            FakeRnaProp("mute", "BOOLEAN"),
            FakeRnaProp("hide", "BOOLEAN"),
            FakeRnaProp("use_custom_color", "BOOLEAN"),
            FakeRnaProp("color", "FLOAT"),
            FakeRnaProp("average_error", "FLOAT", is_readonly=True),
            FakeRnaProp("markers", "COLLECTION", is_readonly=True),
        )


class FakeTracks(list):
    def __init__(self) -> None:
        super().__init__([FakeTrack()])
        self.active = self[0]


class FakeTracking:
    def __init__(self) -> None:
        self.tracks = FakeTracks()
        self.plane_tracks = []
        self.objects = types.SimpleNamespace(active=None, active_object_index=0)
        self.settings = types.SimpleNamespace(default_pattern_size=21, default_search_size=71, default_motion_model="Perspective")
        self.camera = types.SimpleNamespace(sensor_width=36.0, pixel_aspect=1.0)
        self.reconstruction = types.SimpleNamespace(is_valid=False, average_error=0.0)
        self.stabilization = types.SimpleNamespace(use_2d_stabilization=False)
        self.dopesheet = types.SimpleNamespace(sort_method="NAME")


class FakeClip:
    def __init__(self, name: str, filepath: str = "/tmp/plate.png") -> None:
        self.name = name
        self.filepath = filepath
        self.size = [1920, 1080]
        self.display_aspect = [1.0, 1.0]
        self.source = "SEQUENCE"
        self.frame_start = 1
        self.frame_offset = 0
        self.frame_duration = 1
        self.fps = 24.0
        self.tracking = FakeTracking()
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("filepath", "STRING"),
            FakeRnaProp("size", "INT", is_readonly=True),
            FakeRnaProp("display_aspect", "FLOAT"),
            FakeRnaProp("source", "ENUM", is_readonly=True),
            FakeRnaProp("frame_start", "INT"),
            FakeRnaProp("frame_offset", "INT"),
            FakeRnaProp("frame_duration", "INT", is_readonly=True),
            FakeRnaProp("fps", "FLOAT", is_readonly=True),
            FakeRnaProp("tracking", "POINTER", is_readonly=True),
        )


class FakeMovieClips(list):
    def get(self, name: str):
        return next((clip for clip in self if clip.name == name), None)

    def load(self, filepath: str, check_existing: bool = False):
        name = filepath.rsplit("/", 1)[-1]
        existing = self.get(name)
        if check_existing and existing is not None:
            return existing
        clip = FakeClip(name, filepath)
        self.append(clip)
        return clip


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.movieclips = FakeMovieClips()
        self.undo_pushes: list[str] = []

        class _Context:
            scene = types.SimpleNamespace(objects=[], name="Scene")
            view_layer = types.SimpleNamespace(objects=types.SimpleNamespace(active=None))
            window_manager = types.SimpleNamespace(windows=[])

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        class _EdOps:
            @staticmethod
            def undo_push(message: str = "", **kw):
                self.undo_pushes.append(message)

        self.context = _Context()
        self.ops = types.SimpleNamespace(ed=_EdOps())

    @property
    def data(self):
        return types.SimpleNamespace(movieclips=self.movieclips)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_tracking_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "tracking.report",
        "tracking.clip_load",
        "tracking.clips",
        "tracking.marker_report",
        "tracking.track_report",
    } <= names


def test_clip_load_clips_and_report(env, tmp_path) -> None:
    ctx, bpy = env
    path = tmp_path / "plate.png"
    path.write_bytes(b"fake")
    reg = build_default_registry()

    loaded = dispatch_on_main(reg, "tracking.clip_load", {"path": str(path), "name": "Plate"}, ctx)

    assert loaded["clip"]["name"] == "Plate"
    assert loaded["clip"]["filepath"] == str(path)
    assert bpy.undo_pushes == ["niua:tracking.clip_load"]

    clips = dispatch_on_main(reg, "tracking.clips", {}, ctx)
    assert clips["clip_count"] == 1
    assert clips["clips"][0]["name"] == "Plate"

    report = dispatch_on_main(reg, "tracking.report", {}, ctx)
    assert report["clip_count"] == 1
    assert report["clips"][0]["track_count"] == 1
    assert report["clips"][0]["marker_count"] == 2


def test_track_and_marker_reports(env) -> None:
    ctx, bpy = env
    bpy.movieclips.append(FakeClip("Plate"))
    reg = build_default_registry()

    tracks = dispatch_on_main(reg, "tracking.track_report", {"clip": "Plate"}, ctx)
    assert tracks["clip"] == "Plate"
    assert tracks["track_count"] == 1
    assert tracks["active_track"] == "Tracker"
    assert tracks["tracks"][0]["marker_count"] == 2

    markers = dispatch_on_main(reg, "tracking.marker_report", {"clip": "Plate"}, ctx)
    assert markers["clip"] == "Plate"
    assert markers["marker_count"] == 2
    assert markers["tracks"][0]["markers"][0]["frame"] == 1
    assert markers["tracks"][0]["markers"][0]["co"] == [0.1, 0.2]


def test_missing_path_and_clip_fail_without_undo(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    with pytest.raises(BridgeError) as path_exc:
        dispatch_on_main(reg, "tracking.clip_load", {"path": "/no/such/plate.png"}, ctx)

    with pytest.raises(BridgeError) as clip_exc:
        dispatch_on_main(reg, "tracking.track_report", {"clip": "Missing"}, ctx)

    assert path_exc.value.code == INVALID_PARAMS
    assert clip_exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []
