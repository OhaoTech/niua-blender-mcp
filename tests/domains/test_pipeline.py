from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.core import pipeline as pipeline_store
from niua_mcp_bridge.core import session as session_store
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


def _identity() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class FakeVert:
    def __init__(self, co) -> None:
        self.co = tuple(float(c) for c in co)


class FakePoly:
    def __init__(self, vert_indices) -> None:
        self.vertices = list(vert_indices)


class FakeMesh:
    def __init__(self, *, verts=None, polys=None, edges=0, uv_layers=0, materials=0, tag="mesh") -> None:
        self.vertices = [FakeVert(c) for c in (verts or [])]
        self.edges = [object() for _ in range(edges)]
        self.polygons = [FakePoly(p) for p in (polys or [])]
        self.uv_layers = [object() for _ in range(uv_layers)]
        self.materials = [object() for _ in range(materials)]
        self.tag = tag

    def copy(self) -> "FakeMesh":
        return FakeMesh(
            verts=[vert.co for vert in self.vertices],
            polys=[poly.vertices for poly in self.polygons],
            edges=len(self.edges),
            uv_layers=len(self.uv_layers),
            materials=len(self.materials),
            tag=self.tag,
        )


class FakeObj:
    def __init__(self, name, type="MESH", data=None, dimensions=(2.0, 2.0, 2.0)) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeMesh()
        self.dimensions = list(dimensions)
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.matrix_world = _identity()


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active = None
        self.undo_pushes: list[str] = []
        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active

            @active.setter
            def active(self_inner, value):
                bpy._active = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        class _Context:
            scene = self.scene
            view_layer = self.view_layer
            window_manager = types.SimpleNamespace(windows=[])

            @property
            def object(self_inner):
                return bpy._active

        self.context = _Context()

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(ed=_EdOps())

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        self._active = obj
        return obj

    @property
    def data(self):
        store = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    pipeline_store.reset()
    session_store.reset()
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.delitem(sys.modules, "bmesh", raising=False)
    return Ctx(bpy), bpy


_CUBE_VERTS = [
    (-1, -1, -1),
    (1, -1, -1),
    (1, 1, -1),
    (-1, 1, -1),
    (-1, -1, 1),
    (1, -1, 1),
    (1, 1, 1),
    (-1, 1, 1),
]
_CUBE_QUADS = [
    [0, 1, 2, 3],
    [4, 5, 6, 7],
    [0, 1, 5, 4],
    [1, 2, 6, 5],
    [2, 3, 7, 6],
    [3, 0, 4, 7],
]


def _dispatch(env, command: str, payload: dict) -> dict:
    ctx, _bpy = env
    reg = build_default_registry()
    return dispatch_on_main(reg, command, payload, ctx)


def test_pipeline_specs_and_handlers_are_registered():
    spec_names = {spec.name for spec in build_router().specs()}
    reg = build_default_registry()

    for name in ("pipeline.start", "pipeline.status", "pipeline.gate_check"):
        assert name in spec_names
        command = reg.get(name)
        assert command is not None
        assert command.mutates is False


def test_pipeline_start_creates_state_and_intake_checkpoint(env):
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))

    out = _dispatch(env, "pipeline.start", {"object": "Cube"})

    assert out["state"]["current_stage"] == "intake"
    assert out["state"]["profile"] == "game_asset"
    assert out["state"]["checkpoints"]["intake"] == "pipeline:intake:entry"
    assert session_store.get_snapshot("Cube", "pipeline:intake:entry") is not None
    assert bpy.undo_pushes == []


def test_pipeline_status_returns_one_run_or_all_runs(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    single = _dispatch(env, "pipeline.status", {"object": "Cube"})
    all_runs = _dispatch(env, "pipeline.status", {})

    assert single["object"] == "Cube"
    assert single["state"]["current_stage"] == "intake"
    assert [run["object"] for run in all_runs["runs"]] == ["Cube"]


def test_gate_check_intake_passes_and_records_gate(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube"})

    assert out["object"] == "Cube"
    assert out["stage"] == "intake"
    assert out["gates"] == []
    assert out["gates_pass"] is True
    assert out["metrics"]["object"] == "Cube"
    assert out["state"]["state"]["gates"]["intake"]["gates_pass"] is True


def test_gate_check_named_stage_uses_stage_gate_profile(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "repair"})

    assert out["stage"] == "repair"
    assert out["gates_pass"] is False
    assert [gate["path"] for gate in out["gates"]] == [
        "orientation.degenerate_faces",
        "orientation.inward_facing_faces",
    ]
    assert out["gates"][0]["actual"] is None
    assert out["state"]["state"]["gates"]["repair"]["gates_pass"] is False
