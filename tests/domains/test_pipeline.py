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
from niua_mcp_bridge.errors import PRECONDITION, BridgeError


def _identity() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class FakeVert:
    def __init__(self, co) -> None:
        self.co = tuple(float(c) for c in co)


class FakePoly:
    def __init__(self, vert_indices) -> None:
        self.vertices = list(vert_indices)


class FakeImage:
    def __init__(self, name: str, colorspace="sRGB") -> None:
        self.name = name
        self.filepath = f"/tmp/{name}.png"
        self.size = [1024, 1024]
        self.colorspace_settings = types.SimpleNamespace(name=colorspace)


class FakeTexNode:
    type = "TEX_IMAGE"

    def __init__(self, label: str, image: FakeImage) -> None:
        self.name = image.name
        self.label = label
        self.image = image


class FakeMaterial:
    def __init__(self, name: str, maps=()) -> None:
        self.name = name
        self.node_tree = types.SimpleNamespace(nodes=[FakeTexNode(label, image) for label, image in maps])


class FakeMesh:
    def __init__(self, *, verts=None, polys=None, edges=0, uv_layers=0, materials=0, tag="mesh") -> None:
        self.vertices = [FakeVert(c) for c in (verts or [])]
        self.edges = [object() for _ in range(edges)]
        self.polygons = [FakePoly(p) for p in (polys or [])]
        self.uv_layers = [object() for _ in range(uv_layers)]
        self.materials = [object() for _ in range(materials)] if isinstance(materials, int) else list(materials)
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

    expected_mutates = {
        "pipeline.start": False,
        "pipeline.status": False,
        "pipeline.gate_check": False,
        "pipeline.advance": False,
        "pipeline.rollback": True,
        "pipeline.self_critique": False,
    }

    for name, mutates in expected_mutates.items():
        assert name in spec_names
        command = reg.get(name)
        assert command is not None
        assert command.mutates is mutates


def test_pipeline_start_creates_state_and_intake_checkpoint(env):
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))

    out = _dispatch(env, "pipeline.start", {"object": "Cube"})

    assert out["state"]["current_stage"] == "intake"
    assert out["state"]["profile"] == "game_asset"
    assert out["state"]["checkpoints"]["intake"] == "pipeline:intake:entry"
    assert session_store.get_snapshot("Cube", "pipeline:intake:entry") is not None
    assert bpy.undo_pushes == []


def test_pipeline_start_persists_explicit_asset_class(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))

    out = _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "generated_cleanup"})

    state = out["state"]
    assert state["asset_class"] == "generated_cleanup"
    assert state["profile_version"] == 1
    assert state["asset_class_defaulted"] is False


def test_pipeline_start_defaults_asset_class_visibly(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))

    out = _dispatch(env, "pipeline.start", {"object": "Cube"})

    state = out["state"]
    assert state["asset_class"] == "hard_surface_prop"
    assert state["profile_version"] == 1
    assert state["asset_class_defaulted"] is True


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


def test_gate_check_applies_stored_asset_class_gate_overrides(env):
    _ctx, bpy = env
    polys = _CUBE_QUADS + [[0, 1, 2]]
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=polys)))
    _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "generated_cleanup"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "retopo"})

    assert out["asset_class"]["id"] == "generated_cleanup"
    assert out["asset_class"]["applied_gate_overrides"]["retopo"]["topology.quad_ratio"]["value"] == 0.98
    assert out["gates"][0]["path"] == "topology.quad_ratio"
    assert out["gates"][0]["value"] == 0.98
    assert out["gates"][0]["actual"] < 0.98


def test_gate_check_accepts_payload_asset_class_override(env):
    _ctx, bpy = env
    polys = _CUBE_QUADS + [[0, 1, 2]]
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=polys)))
    _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "hard_surface_prop"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "retopo", "asset_class": "organic_prop"})

    assert out["asset_class"]["id"] == "organic_prop"
    assert out["gates"][0]["value"] == 0.85
    assert out["gates"][0]["pass"] is True


def test_gate_check_optimize_uses_engine_readiness_metrics(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    bpy.add(FakeObj("Cube_LOD1", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS[:2])))
    bpy.add(FakeObj("Cube_COL", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "optimize"})

    assert out["stage"] == "optimize"
    assert out["gates_pass"] is True
    assert out["metrics"]["engine"]["lod_count"] == 1
    assert out["metrics"]["engine"]["collision_proxy_count"] == 1
    assert out["metrics"]["engine"]["lod_triangle_reduction_ok"] is True
    assert out["metrics"]["engine"]["collision_bounds_valid"] is True
    assert [gate["path"] for gate in out["gates"]] == [
        "engine.within_triangle_budget",
        "engine.within_material_budget",
        "engine.within_texture_budget",
        "engine.has_lods",
        "engine.has_collision_proxy",
        "engine.lod_triangle_reduction_ok",
        "engine.lod_silhouette_preserved",
        "engine.has_collision_hulls",
        "engine.collision_bounds_valid",
    ]


def test_gate_check_optimize_accepts_budget_overrides(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    bpy.add(FakeObj("Cube_LOD1", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS[:2])))
    bpy.add(FakeObj("Cube_COL", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "optimize", "triangle_budget": 8})

    assert out["gates_pass"] is False
    assert out["metrics"]["engine"]["triangle_budget"] == 8
    assert out["metrics"]["engine"]["triangles"] == 12
    assert out["gates"][0]["path"] == "engine.within_triangle_budget"
    assert out["gates"][0]["actual"] is False


def test_gate_check_bake_and_material_use_material_production_metrics(env):
    _ctx, bpy = env
    material = FakeMaterial(
        "HeroMat",
        [
            ("BASE_COLOR", FakeImage("hero_base_color", "sRGB")),
            ("NORMAL", FakeImage("hero_normal", "Non-Color")),
            ("ROUGHNESS", FakeImage("hero_roughness", "Non-Color")),
            ("AO", FakeImage("hero_ao", "Non-Color")),
            ("CAVITY", FakeImage("hero_cavity", "Non-Color")),
        ],
    )
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS, materials=[material])))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    bake = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "bake"})
    material_gate = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "material"})

    assert bake["gates_pass"] is True
    assert bake["metrics"]["material"]["bake_maps_present"] is True
    assert [gate["path"] for gate in bake["gates"]] == [
        "material.bake_maps_present",
        "material.data_maps_non_color",
    ]
    assert material_gate["gates_pass"] is True
    assert material_gate["metrics"]["material"]["atlas_ready"] is True
    assert [gate["path"] for gate in material_gate["gates"]] == [
        "material.pbr_maps_present",
        "material.textures_within_size",
        "material.atlas_ready",
    ]


def test_pipeline_advance_creates_next_stage_checkpoint(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    out = _dispatch(env, "pipeline.advance", {"object": "Cube"})

    assert out["from_stage"] == "intake"
    assert out["to_stage"] == "repair"
    assert out["state"]["state"]["current_stage"] == "repair"
    assert out["gate"]["gates_pass"] is True
    assert session_store.get_snapshot("Cube", "pipeline:repair:entry") is not None
    assert bpy.undo_pushes == []


def test_pipeline_advance_is_blocked_by_failing_gate(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})
    _dispatch(env, "pipeline.advance", {"object": "Cube"})

    with pytest.raises(BridgeError) as exc:
        _dispatch(env, "pipeline.advance", {"object": "Cube"})

    assert exc.value.code == PRECONDITION
    assert "repair" in exc.value.message
    assert session_store.get_snapshot("Cube", "pipeline:retopo:entry") is None
    assert pipeline_store.get_state("Cube")["current_stage"] == "repair"


def test_pipeline_rollback_restores_stage_checkpoint_and_pushes_undo(env):
    _ctx, bpy = env
    obj = bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS, tag="base")))
    _dispatch(env, "pipeline.start", {"object": "Cube"})
    _dispatch(env, "pipeline.advance", {"object": "Cube"})
    obj.data = FakeMesh(verts=[], polys=[], tag="edited")

    out = _dispatch(env, "pipeline.rollback", {"object": "Cube", "stage": "repair"})

    assert out["object"] == "Cube"
    assert out["stage"] == "repair"
    assert out["state"]["state"]["current_stage"] == "repair"
    assert obj.data.tag == "base"
    assert len(obj.data.vertices) == len(_CUBE_VERTS)
    assert bpy.undo_pushes == ["niua:pipeline.rollback"]


def test_pipeline_self_critique_returns_repair_guidance_for_failed_uv(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    _dispatch(env, "pipeline.start", {"object": "Cube"})

    out = _dispatch(env, "pipeline.self_critique", {"object": "Cube", "stage": "uv"})

    assert out["stage"] == "uv"
    assert out["gate"]["gates_pass"] is False
    assert out["critique"]["failed_count"] >= 1
    assert any("unwrap" in rec.lower() for rec in out["critique"]["recommendations"])
