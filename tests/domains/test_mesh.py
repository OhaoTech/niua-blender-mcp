"""Mesh domain unit tests (fake-bpy).

Extends the FakeBpy pattern from tests/test_dispatch.py with mesh data (polygons,
vertices, edges, uv_layers, materials, dimensions, matrix_world) so mesh.report has
something to count, plus the edit/object operators the handlers call. Operators are
callable AND carry a ``poll`` attribute (so ctx.check_poll passes). ``bpy`` is injected
into sys.modules so the lazily-imported context resolver runs against the same fake.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import NOT_FOUND, PRECONDITION, BridgeError


def _identity() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


class FakePoly:
    def __init__(self, vert_indices) -> None:
        self.vertices = list(vert_indices)


class FakeMesh:
    def __init__(self, *, verts=0, edges=0, polys=None, uv_layers=0, materials=0) -> None:
        self.vertices = [object() for _ in range(verts)]
        self.edges = [object() for _ in range(edges)]
        self.polygons = [FakePoly(p) for p in (polys or [])]
        self.uv_layers = [object() for _ in range(uv_layers)]
        self.materials = [object() for _ in range(materials)]


class FakeObj:
    def __init__(self, name: str, type: str = "MESH", data: FakeMesh | None = None) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeMesh()
        self.dimensions = [2.0, 2.0, 2.0]
        self.matrix_world = _identity()
        self._selected = False
        self.mode = "OBJECT"

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class _Op:
    """A callable operator that records calls and polls True by default."""

    def __init__(self, log: list, name: str, poll_ok: bool = True) -> None:
        self._log = log
        self._name = name
        self._poll_ok = poll_ok

    def poll(self) -> bool:
        return self._poll_ok

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active_obj = None
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []

        bpy = self

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

        log = self.op_calls

        class _MeshOps:
            extrude_region_move = _Op(log, "mesh.extrude_region_move")
            bevel = _Op(log, "mesh.bevel")
            inset = _Op(log, "mesh.inset")
            subdivide = _Op(log, "mesh.subdivide")
            select_all = _Op(log, "mesh.select_all")
            normals_make_consistent = _Op(log, "mesh.normals_make_consistent")

        class _ObjectOps:
            shade_smooth = _Op(log, "object.shade_smooth")
            shade_flat = _Op(log, "object.shade_flat")

            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

            def undo(self_inner, **kw):
                pass

        self.ops = types.SimpleNamespace(mesh=_MeshOps(), object=_ObjectOps(), ed=_EdOps())

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        store = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))
            materials: dict = {}

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    monkeypatch.delitem(sys.modules, "bmesh", raising=False)
    return Ctx(bpy), bpy


def _names(log):
    return [n for n, _ in log]


# -- edit-mode operators -----------------------------------------------------------


def test_extrude_runs_edit_op_and_pushes_one_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "mesh.extrude", {"object": "Cube", "translate": [0, 0, 1]}, ctx)
    assert result["object"] == "Cube"
    assert "mesh.extrude_region_move" in _names(bpy.op_calls)
    assert bpy.mode_calls == ["EDIT", "OBJECT"]  # entered EDIT, restored to OBJECT
    assert bpy.undo_pushes == ["niua:mesh.extrude"]


def test_extrude_passes_translation_value(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "mesh.extrude", {"object": "Cube", "translate": [1, 2, 3]}, ctx)
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "mesh.extrude_region_move")
    assert kwargs["TRANSFORM_OT_translate"]["value"] == (1.0, 2.0, 3.0)


def test_bevel_passes_offset_and_segments(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "mesh.bevel", {"object": "Cube", "offset": 0.25, "segments": 3}, ctx)
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "mesh.bevel")
    assert kwargs == {"offset": 0.25, "segments": 3}


def test_inset_passes_thickness(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "mesh.inset", {"object": "Cube", "thickness": 0.4}, ctx)
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "mesh.inset")
    assert kwargs == {"thickness": 0.4}


def test_subdivide_passes_cuts(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "mesh.subdivide", {"object": "Cube", "cuts": 4}, ctx)
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "mesh.subdivide")
    assert kwargs == {"number_cuts": 4}


def test_recalc_normals_selects_all_then_recalcs(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "mesh.recalc_normals", {"object": "Cube", "inside": True}, ctx)
    names = _names(bpy.op_calls)
    assert "mesh.select_all" in names and "mesh.normals_make_consistent" in names
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "mesh.normals_make_consistent")
    assert kwargs == {"inside": True}


def test_extrude_defaults_to_active_object(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))  # becomes active
    reg = build_default_registry()
    result = dispatch_on_main(reg, "mesh.extrude", {}, ctx)
    assert result["object"] == "Cube"


# -- shading (object mode) ---------------------------------------------------------


def test_shade_smooth_true_calls_shade_smooth(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "mesh.shade_smooth", {"object": "Cube", "smooth": True}, ctx)
    assert result["smooth"] is True
    assert "object.shade_smooth" in _names(bpy.op_calls)


def test_shade_smooth_false_calls_shade_flat(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "mesh.shade_smooth", {"object": "Cube", "smooth": False}, ctx)
    assert "object.shade_flat" in _names(bpy.op_calls)


# -- precondition handling ---------------------------------------------------------


def test_non_mesh_object_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Light", type="LIGHT"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "mesh.subdivide", {"object": "Light"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []  # no mutation, no undo step


def test_missing_object_raises_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "mesh.subdivide", {"object": "Ghost"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_no_active_object_raises_precondition(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "mesh.subdivide", {}, ctx)
    assert exc.value.code == PRECONDITION


def test_failing_poll_raises_clean_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    bpy.ops.mesh.subdivide._poll_ok = False
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "mesh.subdivide", {"object": "Cube"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


# -- analytic report (read-only) ---------------------------------------------------


def test_report_counts_topology(env) -> None:
    ctx, bpy = env
    # 2 quads + 1 triangle + 1 pentagon(ngon). verts/edges arbitrary counts.
    mesh = FakeMesh(
        verts=8,
        edges=12,
        polys=[[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 2], [0, 1, 2, 3, 4]],
        uv_layers=2,
        materials=3,
    )
    bpy.add(FakeObj("Cube", data=mesh))
    reg = build_default_registry()
    rep = dispatch_on_main(reg, "mesh.report", {"object": "Cube"}, ctx)
    assert rep["vertices"] == 8
    assert rep["edges"] == 12
    assert rep["faces"] == 4
    # triangles = sum(len-2): quad=2, quad=2, tri=1, pentagon=3 -> 8
    assert rep["triangles"] == 8
    assert rep["ngons"] == 1  # only the pentagon has >4 verts
    assert rep["uv_layers"] == 2
    assert rep["materials"] == 3
    assert rep["bbox_dimensions"] == [2.0, 2.0, 2.0]
    assert rep["transform_applied"] is True  # identity matrix_world
    assert rep["non_manifold_edges"] is None  # bmesh not importable in fake env


def test_report_is_read_only_no_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "mesh.report", {"object": "Cube"}, ctx)
    assert bpy.undo_pushes == []


def test_report_detects_unapplied_transform(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.matrix_world = _identity()
    obj.matrix_world[0][3] = 5.0  # translated -> not identity
    bpy.add(obj)
    reg = build_default_registry()
    rep = dispatch_on_main(reg, "mesh.report", {"object": "Cube"}, ctx)
    assert rep["transform_applied"] is False
