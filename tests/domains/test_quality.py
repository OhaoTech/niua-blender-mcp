"""feedback.quality unit tests (fake-bpy).

A fake mesh with known vertex coordinates and faces drives the pure-geometry metrics:
topology counts / ratios, symmetry across each local plane (symmetric vs lopsided mesh),
and proportion. bmesh is absent in this env, so pole_count / non_manifold_edges /
loose_verts degrade to ``null`` (asserted) while every pure-Python field still computes.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.core import pipeline as pipeline_store
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, PRECONDITION, BridgeError


def _identity() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class FakeVert:
    def __init__(self, co) -> None:
        self.co = tuple(float(c) for c in co)


class FakePoly:
    def __init__(self, vert_indices) -> None:
        self.vertices = list(vert_indices)


class FakeImage:
    def __init__(self, name: str, size=(1024, 1024), colorspace="sRGB") -> None:
        self.name = name
        self.filepath = f"/tmp/{name}.png"
        self.size = list(size)
        self.colorspace_settings = types.SimpleNamespace(name=colorspace)


class FakeTexNode:
    type = "TEX_IMAGE"

    def __init__(self, image: FakeImage, label: str = "") -> None:
        self.name = image.name
        self.label = label
        self.image = image


class FakeMaterial:
    def __init__(self, name: str, images=()) -> None:
        self.name = name
        nodes = []
        for item in images:
            if isinstance(item, tuple):
                label, image = item
                nodes.append(FakeTexNode(image, label))
            else:
                nodes.append(FakeTexNode(item))
        self.node_tree = types.SimpleNamespace(nodes=nodes)


class FakeMesh:
    def __init__(self, *, verts=None, polys=None, edges=0, uv_layers=0, materials=0) -> None:
        self.vertices = [FakeVert(c) for c in (verts or [])]
        self.edges = [object() for _ in range(edges)]
        self.polygons = [FakePoly(p) for p in (polys or [])]
        self.uv_layers = [object() for _ in range(uv_layers)]
        self.materials = [object() for _ in range(materials)] if isinstance(materials, int) else list(materials)


class FakeObj:
    def __init__(self, name, type="MESH", data=None, dimensions=(2.0, 2.0, 2.0)) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeMesh()
        self.dimensions = list(dimensions)
        self.matrix_world = _identity()


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active = None
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

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()
        self.ops = types.SimpleNamespace(
            ed=types.SimpleNamespace(undo_push=lambda **kw: None, undo=lambda **kw: None)
        )

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
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.delitem(sys.modules, "bmesh", raising=False)
    return Ctx(bpy), bpy


# A small symmetric "box-ish" patch: every vert has its X-mirror partner.
_SYMMETRIC_VERTS = [
    (-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0),  # quad on z=0
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),  # quad on z=1
]
_SYMMETRIC_POLYS = [[0, 1, 2, 3], [4, 5, 6, 7]]  # two quads


def _quality(env, name, **payload):
    ctx, bpy = env
    reg = build_default_registry()
    return dispatch_on_main(reg, "feedback.quality", {"object": name, **payload}, ctx)


def test_quality_applies_asset_class_defaults(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS * 1500)
    bpy.add(FakeObj("Cube", data=mesh))

    organic = _quality(env, "Cube", asset_class="organic_prop")["engine"]
    scratch = _quality(env, "Cube", asset_class="from_scratch_prop")["engine"]

    assert organic["triangle_budget"] == 8000
    assert organic["within_triangle_budget"] is True
    assert scratch["triangle_budget"] == 4000
    assert scratch["within_triangle_budget"] is False


def test_quality_reports_asset_class_metadata_and_explicit_overrides(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))

    out = _quality(env, "Cube", asset_class="organic_prop", triangle_budget=1234)

    meta = out["asset_class"]
    assert meta["id"] == "organic_prop"
    assert meta["profile_version"] == 1
    assert meta["asset_class_defaulted"] is False
    assert meta["effective_defaults"]["triangle_budget"] == 1234
    assert meta["effective_defaults"]["material_budget"] == 3
    assert meta["applied_gate_overrides"] == {}


def test_quality_ignores_pipeline_state_and_defaults_when_payload_omits_class(env) -> None:
    # Decoupling: feedback.quality is base-layer and must resolve asset_class from the
    # payload ONLY, never by reaching into the Layer-2 pipeline FSM singleton. Even
    # though a pipeline run is active with a non-default asset_class, a direct
    # feedback.quality call with no asset_class in the payload falls back to the
    # DEFAULT profile, not the pipeline's stored one. (The pipeline-aware path is
    # pipeline.gate_check, which resolves the class itself and passes it through the
    # payload explicitly -- see test_pipeline.py.)
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS * 1501)))
    reg = build_default_registry()

    dispatch_on_main(reg, "pipeline.start", {"object": "Cube", "asset_class": "generated_cleanup"}, ctx)
    out = dispatch_on_main(reg, "feedback.quality", {"object": "Cube"}, ctx)

    meta = out["asset_class"]
    assert meta["id"] == "hard_surface_prop"
    assert meta["asset_class_defaulted"] is True
    assert meta["effective_defaults"]["triangle_budget"] == 5000
    assert out["engine"]["triangle_budget"] == 5000


def test_quality_defaults_asset_class_with_no_payload_and_no_pipeline_run(env) -> None:
    # Part (b): no asset_class in the payload AND no pipeline run at all -- must not
    # error, and must fall back to the default profile.
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))

    out = _quality(env, "Cube")

    meta = out["asset_class"]
    assert meta["id"] == "hard_surface_prop"
    assert meta["asset_class_defaulted"] is True
    assert meta["effective_defaults"]["triangle_budget"] == 5000


def test_quality_explicit_payload_asset_class_is_used(env) -> None:
    # Part (a): an explicit asset_class in the payload is honored -- the engine/material
    # blocks reflect that class's overrides -- regardless of any pipeline state.
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS * 1501)))

    out = _quality(env, "Cube", asset_class="generated_cleanup")

    meta = out["asset_class"]
    assert meta["id"] == "generated_cleanup"
    assert meta["asset_class_defaulted"] is False
    assert meta["effective_defaults"]["triangle_budget"] == 6000
    assert out["engine"]["triangle_budget"] == 6000
    assert out["engine"]["within_triangle_budget"] is False


def test_feedback_module_does_not_import_pipeline() -> None:
    # The base (feedback.py) must not depend on the Layer-2 pipeline FSM singleton -- its
    # control surface (start/advance/status/record_gate/rollback_pointer/reset/_STORE) and the
    # domains.pipeline module stay untouched. feedback.readiness is the sanctioned exception:
    # it reuses the pure, order-free gate DEFINITIONS (stage_gates/check_gates/gate_profile)
    # that happen to live in core/pipeline.py alongside the FSM -- never the FSM control itself.
    import ast
    import inspect

    import niua_mcp_bridge.domains.feedback as feedback_mod

    _ALLOWED_CORE_PIPELINE_NAMES = {"check_gates", "gate_profile", "stage_gates"}

    source = inspect.getsource(feedback_mod)
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            if node.module == "core.pipeline":
                names = {alias.name for alias in node.names}
                assert names <= _ALLOWED_CORE_PIPELINE_NAMES, names
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    banned = {name for name in imported_modules if "pipeline" in name and name != "core.pipeline"}
    assert not banned, banned
    assert not hasattr(feedback_mod, "pipeline_store")
    for fsm_symbol in ("start", "advance", "status", "record_gate", "rollback_pointer", "reset", "get_state"):
        assert not hasattr(feedback_mod, fsm_symbol), fsm_symbol


def test_quality_unknown_asset_class_fails_cleanly(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "feedback.quality", {"object": "Cube", "asset_class": "nope"}, ctx)

    assert exc.value.code == INVALID_PARAMS
    assert "unknown asset class: nope" in str(exc.value)


def test_topology_ratios_quads_tris_ngons(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(
        verts=_SYMMETRIC_VERTS,
        # 2 quads + 1 tri + 1 pentagon(ngon)
        polys=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 2], [0, 1, 2, 3, 4]],
    )
    bpy.add(FakeObj("Cube", data=mesh))
    q = _quality(env, "Cube")["topology"]
    assert q["faces"] == 4
    assert q["quads"] == 2
    assert q["ngons"] == 1
    # tris (triangulated): quad=2,quad=2,tri=1,pentagon=3 -> 8
    assert q["tris"] == 8
    assert q["quad_ratio"] == pytest.approx(0.5)
    assert q["ngon_ratio"] == pytest.approx(0.25)


def test_bmesh_fields_degrade_to_null_without_bmesh(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    q = _quality(env, "Cube")["topology"]
    assert q["pole_count"] is None
    assert q["non_manifold_edges"] is None
    assert q["loose_verts"] is None


def test_symmetric_mesh_is_symmetric_on_all_axes(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    sym = _quality(env, "Cube")["symmetry"]
    # X and Y mirror partners exist for every vert.
    assert sym["symmetry_x"] == pytest.approx(1.0)
    assert sym["symmetry_y"] == pytest.approx(1.0)
    # Z: z=0 and z=1 are NOT mirror images across z=0, so this is < 1.0 (only the z=0 ring
    # self-mirrors). The point: the metric distinguishes axes.
    assert sym["symmetry_z"] < 1.0


def test_lopsided_mesh_has_low_x_symmetry(env) -> None:
    ctx, bpy = env
    # Shove the +X verts outward only on the right: no left partner for them.
    lopsided = [
        (-1, -1, 0), (5, -1, 0), (5, 1, 0), (-1, 1, 0),
        (-1, -1, 1), (5, -1, 1), (5, 1, 1), (-1, 1, 1),
    ]
    bpy.add(FakeObj("Lop", data=FakeMesh(verts=lopsided, polys=_SYMMETRIC_POLYS)))
    sym = _quality(env, "Lop")["symmetry"]
    assert sym["symmetry_x"] < 1.0  # lopsided across YZ plane
    assert sym["symmetry_y"] == pytest.approx(1.0)  # still mirrored in Y


def test_proportion_and_scale_blocks(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS),
                  dimensions=(4.0, 2.0, 1.0))
    bpy.add(obj)
    out = _quality(env, "Cube")
    prop = out["proportion"]
    assert prop["bbox_dimensions"] == [4.0, 2.0, 1.0]
    assert prop["aspect_ratio"] == pytest.approx(4.0)  # longest/shortest = 4/1
    assert prop["boxiness"] is not None
    scale = out["scale"]
    assert scale["bbox_dimensions"] == [4.0, 2.0, 1.0]
    assert scale["transform_applied"] is True  # identity matrix_world


def test_quality_includes_uv_block_with_fake_bpy_degrade(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS, uv_layers=1)))
    out = _quality(env, "Cube")
    assert out["uv"]["has_uvs"] is True
    assert out["uv"]["uv_layer_count"] == 1
    assert out["uv"]["texel_density_px_per_unit"] is None


def test_quality_includes_orientation_block_with_fake_bpy_degrade(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    out = _quality(env, "Cube")
    assert out["orientation"] == {
        "degenerate_faces": None,
        "inward_facing_faces": None,
        "inward_facing_ratio": None,
        "normal_consistency": None,
    }


def test_quality_includes_engine_readiness_metrics(env) -> None:
    ctx, bpy = env
    albedo = FakeImage("crate_albedo")
    normal = FakeImage("crate_normal")
    mesh = FakeMesh(
        verts=_SYMMETRIC_VERTS,
        polys=_SYMMETRIC_POLYS,
        materials=[
            FakeMaterial("Body", [albedo, normal]),
            FakeMaterial("Trim", [albedo]),
        ],
    )
    bpy.add(FakeObj("Cube", data=mesh))
    bpy.add(FakeObj("Cube_LOD1", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=[_SYMMETRIC_POLYS[0]])))
    bpy.add(FakeObj("UCX_Cube_00", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))

    engine = _quality(
        env,
        "Cube",
        triangle_budget=12,
        material_budget=2,
        texture_budget=2,
        min_lods=1,
    )["engine"]

    expected = {
        "triangles": 4,
        "triangle_budget": 12,
        "within_triangle_budget": True,
        "materials": 2,
        "material_budget": 2,
        "within_material_budget": True,
        "textures": 2,
        "texture_budget": 2,
        "within_texture_budget": True,
        "lod_count": 1,
        "min_lods": 1,
        "has_lods": True,
        "collision_proxy_count": 1,
        "has_collision_proxy": True,
    }
    for key, value in expected.items():
        assert engine[key] == value
    assert engine["lods"] == [
        {
            "name": "Cube_LOD1",
            "level": 1,
            "triangles": 2,
            "triangle_ratio": 0.5,
            "bounds_delta": 0.0,
        }
    ]
    assert engine["lod_triangle_reduction_ok"] is True
    assert engine["lod_silhouette_preserved"] is True
    assert engine["min_collision_hulls"] == 1
    assert engine["has_collision_hulls"] is True
    assert engine["collision_covers_source"] is True
    assert engine["collision_tight"] is True
    assert engine["collision_bounds_valid"] is True


def test_engine_readiness_budget_failures_are_explicit(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(
        verts=_SYMMETRIC_VERTS,
        polys=_SYMMETRIC_POLYS * 3,
        materials=[FakeMaterial("Body", [FakeImage("a")]), FakeMaterial("Trim", [FakeImage("b")])],
    )
    bpy.add(FakeObj("Cube", data=mesh))

    engine = _quality(
        env,
        "Cube",
        triangle_budget=4,
        material_budget=1,
        texture_budget=1,
        min_lods=1,
    )["engine"]

    assert engine["triangles"] == 12
    assert engine["within_triangle_budget"] is False
    assert engine["within_material_budget"] is False
    assert engine["within_texture_budget"] is False
    assert engine["has_lods"] is False
    assert engine["has_collision_proxy"] is False
    assert engine["lod_triangle_reduction_ok"] is False
    assert engine["lod_silhouette_preserved"] is False
    assert engine["has_collision_hulls"] is False
    assert engine["collision_bounds_valid"] is False


def test_engine_readiness_lod_and_collision_quality_failures_are_explicit(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)
    bpy.add(FakeObj("Cube", data=mesh, dimensions=(4.0, 4.0, 4.0)))
    bpy.add(FakeObj("Cube_LOD1", data=mesh, dimensions=(2.0, 4.0, 4.0)))
    bpy.add(FakeObj("Cube_COL", data=mesh, dimensions=(10.0, 10.0, 10.0)))

    engine = _quality(
        env,
        "Cube",
        min_lods=1,
        max_lod_triangle_ratio=0.5,
        max_lod_bounds_delta=0.1,
        min_collision_hulls=2,
        max_collision_oversize_ratio=0.25,
    )["engine"]

    assert engine["lods"][0]["triangle_ratio"] == 1.0
    assert engine["lods"][0]["bounds_delta"] == 0.5
    assert engine["lod_triangle_reduction_ok"] is False
    assert engine["lod_silhouette_preserved"] is False
    assert engine["collision_proxy_count"] == 1
    assert engine["min_collision_hulls"] == 2
    assert engine["has_collision_hulls"] is False
    assert engine["collision_covers_source"] is True
    assert engine["collision_oversize_ratio"] == 1.5
    assert engine["collision_tight"] is False
    assert engine["collision_bounds_valid"] is False


def test_engine_readiness_allows_optional_lod_and_collision_requirements(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))

    engine = _quality(env, "Cube", min_lods=0, min_collision_hulls=0)["engine"]

    assert engine["has_lods"] is True
    assert engine["lod_triangle_reduction_ok"] is True
    assert engine["lod_silhouette_preserved"] is True
    assert engine["has_collision_hulls"] is True
    assert engine["collision_bounds_valid"] is True


def test_quality_includes_material_production_metrics(env) -> None:
    ctx, bpy = env
    material = FakeMaterial(
        "HeroMat",
        [
            ("BASE_COLOR", FakeImage("hero_base_color", colorspace="sRGB")),
            ("NORMAL", FakeImage("hero_normal", colorspace="Non-Color")),
            ("ROUGHNESS", FakeImage("hero_roughness", colorspace="Non-Color")),
            ("AO", FakeImage("hero_ao", colorspace="Non-Color")),
            ("CAVITY", FakeImage("hero_cavity", colorspace="Non-Color")),
        ],
    )
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS, materials=[material])))

    material_quality = _quality(env, "Cube", max_texture_size=1024)["material"]

    assert material_quality["material_count"] == 1
    assert material_quality["texture_count"] == 5
    assert material_quality["present_maps"] == ["AO", "BASE_COLOR", "CAVITY", "NORMAL", "ROUGHNESS"]
    assert material_quality["missing_maps"] == []
    assert material_quality["bake_maps_present"] is True
    assert material_quality["pbr_maps_present"] is True
    assert material_quality["data_maps_non_color"] is True
    assert material_quality["textures_within_size"] is True
    assert material_quality["atlas_ready"] is True


def test_material_metrics_expose_missing_maps_and_bad_colorspace(env) -> None:
    ctx, bpy = env
    material = FakeMaterial(
        "HeroMat",
        [
            ("BASE_COLOR", FakeImage("hero_base_color", colorspace="sRGB")),
            ("NORMAL", FakeImage("hero_normal", colorspace="sRGB")),
            ("ROUGHNESS", FakeImage("hero_roughness", size=(4096, 4096), colorspace="Non-Color")),
        ],
    )
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS, materials=[material])))

    material_quality = _quality(env, "Cube", max_texture_size=2048)["material"]

    assert material_quality["missing_maps"] == ["AO", "CAVITY"]
    assert material_quality["bake_maps_present"] is False
    assert material_quality["pbr_maps_present"] is False
    assert material_quality["data_maps_non_color"] is False
    assert material_quality["textures_within_size"] is False
    assert material_quality["atlas_ready"] is False


def test_quality_includes_export_profile_metrics(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("HeroAsset", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    bpy.add(FakeObj("HeroAsset_LOD1", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=[_SYMMETRIC_POLYS[0]])))
    bpy.add(FakeObj("HeroAsset_COL", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))

    profile = _quality(
        env,
        "HeroAsset",
        export_profile="GODOT",
        export_format="GLB",
        export_y_up=True,
    )["export_profile"]

    assert profile["profile"] == "GODOT"
    assert profile["format"] == "GLB"
    assert profile["profile_pass"] is True
    assert profile["conventions"]["allowed_formats"] == ["GLB", "GLTF_SEPARATE"]


def test_quality_export_profile_reports_profile_failures(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Bad Name", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))

    profile = _quality(
        env,
        "Bad Name",
        export_profile="CUSTOM",
        export_format="OBJ",
        allowed_formats="GLB,FBX",
        name_regex="^[A-Za-z0-9_]+$",
        min_lods=0,
        require_collision=False,
    )["export_profile"]

    assert profile["profile"] == "CUSTOM"
    assert profile["profile_pass"] is False
    failed = [check["path"] for check in profile["checks"] if not check["pass"]]
    assert "export_profile.format_allowed" in failed
    assert "export_profile.name_matches" in failed


def test_quality_is_read_only_no_undo(env) -> None:
    ctx, bpy = env
    pushes: list = []
    bpy.ops.ed.undo_push = lambda **kw: pushes.append(kw)
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS)))
    _quality(env, "Cube")
    assert pushes == []


def test_quality_non_mesh_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Lamp", type="LIGHT", data=FakeMesh()))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "feedback.quality", {"object": "Lamp"}, ctx)
    assert exc.value.code == PRECONDITION
