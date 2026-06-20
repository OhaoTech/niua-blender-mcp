"""UV domain unit tests (fake-bpy).

Extends the FakeBpy pattern from tests/test_mesh.py with UV operators (smart_project,
unwrap, cube_project, sphere_project, pack_islands, average_islands_scale) plus
mesh.select_all (the handlers select-all-faces before projecting). Each op is callable
AND carries a ``poll`` attribute so ctx.check_poll passes. ``bpy`` is injected into
sys.modules so the lazily-imported context resolver runs against the same fake. bmesh
is deleted from sys.modules so uv.report's island_count degrades to None in this env.
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


class FakeUVLayers(list):
    """A list of UV layers that also carries an ``active`` attribute, like bpy."""

    def __init__(self, names=None) -> None:
        names = names or []
        super().__init__(types.SimpleNamespace(name=n) for n in names)
        self.active = self[-1] if self else None
        self.new_calls = []

    def get(self, name: str):
        return next((layer for layer in self if layer.name == name), None)

    def new(self, name: str = "UVMap", do_init: bool = True):
        self.new_calls.append({"name": name, "do_init": do_init})
        layer = types.SimpleNamespace(name=name)
        self.append(layer)
        if self.active is None:
            self.active = layer
        return layer

    def remove(self, layer) -> None:
        index = self.index(layer)
        super().remove(layer)
        if self.active is layer:
            self.active = self[min(index, len(self) - 1)] if self else None


class FakeMesh:
    def __init__(self, *, uv_layer_names=None) -> None:
        self.uv_layers = FakeUVLayers(uv_layer_names)


class FakeObj:
    def __init__(self, name: str, type: str = "MESH", data: FakeMesh | None = None) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeMesh()
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
            select_all = _Op(log, "mesh.select_all")

        class _UVOps:
            smart_project = _Op(log, "uv.smart_project")
            unwrap = _Op(log, "uv.unwrap")
            cube_project = _Op(log, "uv.cube_project")
            sphere_project = _Op(log, "uv.sphere_project")
            pack_islands = _Op(log, "uv.pack_islands")
            average_islands_scale = _Op(log, "uv.average_islands_scale")

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

        self.ops = types.SimpleNamespace(
            mesh=_MeshOps(), uv=_UVOps(), object=_ObjectOps(), ed=_EdOps()
        )

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


def _kwargs(log, op_name):
    return next(k for n, k in log if n == op_name)


# -- edit-mode unwrap / projection ops ---------------------------------------------


def test_smart_unwrap_runs_and_pushes_one_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "uv.smart_unwrap", {"object": "Cube", "angle_limit": 45.0, "island_margin": 0.02}, ctx
    )
    assert result == {"object": "Cube", "angle_limit": 45.0, "island_margin": 0.02}
    names = _names(bpy.op_calls)
    assert "mesh.select_all" in names and "uv.smart_project" in names
    assert bpy.mode_calls == ["EDIT", "OBJECT"]  # entered EDIT, restored to OBJECT
    assert bpy.undo_pushes == ["niua:uv.smart_unwrap"]
    assert _kwargs(bpy.op_calls, "uv.smart_project") == {
        "angle_limit": 45.0,
        "island_margin": 0.02,
    }


def test_smart_unwrap_defaults_to_active_object(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))  # becomes active
    reg = build_default_registry()
    result = dispatch_on_main(reg, "uv.smart_unwrap", {}, ctx)
    assert result["object"] == "Cube"
    assert result["angle_limit"] == 66.0
    assert result["island_margin"] == 0.0


def test_unwrap_passes_method_and_margin(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(
        reg, "uv.unwrap", {"object": "Cube", "method": "CONFORMAL", "island_margin": 0.1}, ctx
    )
    assert _kwargs(bpy.op_calls, "uv.unwrap") == {"method": "CONFORMAL", "margin": 0.1}


def test_unwrap_defaults_to_angle_based(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "uv.unwrap", {"object": "Cube"}, ctx)
    assert result["method"] == "ANGLE_BASED"
    assert _kwargs(bpy.op_calls, "uv.unwrap")["method"] == "ANGLE_BASED"


def test_cube_project_passes_cube_size(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "uv.cube_project", {"object": "Cube", "cube_size": 2.5}, ctx)
    assert _kwargs(bpy.op_calls, "uv.cube_project") == {"cube_size": 2.5}


def test_sphere_project_runs(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "uv.sphere_project", {"object": "Cube"}, ctx)
    assert result == {"object": "Cube", "projected": True}
    assert "uv.sphere_project" in _names(bpy.op_calls)


def test_pack_islands_passes_margin(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(reg, "uv.pack_islands", {"object": "Cube", "margin": 0.05}, ctx)
    assert _kwargs(bpy.op_calls, "uv.pack_islands") == {"margin": 0.05}


def test_pack_islands_default_margin(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "uv.pack_islands", {"object": "Cube"}, ctx)
    assert result["margin"] == 0.001


def test_average_islands_scale_runs(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "uv.average_islands_scale", {"object": "Cube"}, ctx)
    assert result == {"object": "Cube", "averaged": True}
    assert "uv.average_islands_scale" in _names(bpy.op_calls)


# -- precondition handling ---------------------------------------------------------


def test_non_mesh_object_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Light", type="LIGHT"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "uv.smart_unwrap", {"object": "Light"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []  # no mutation, no undo step


def test_missing_object_raises_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "uv.unwrap", {"object": "Ghost"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_no_active_object_raises_precondition(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "uv.cube_project", {}, ctx)
    assert exc.value.code == PRECONDITION


def test_failing_poll_raises_clean_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    bpy.ops.uv.smart_project._poll_ok = False
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "uv.smart_unwrap", {"object": "Cube"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


# -- analytic report (read-only) ---------------------------------------------------


def test_report_with_uvs(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(uv_layer_names=["UVMap", "Lightmap"])
    bpy.add(FakeObj("Cube", data=mesh))
    reg = build_default_registry()
    rep = dispatch_on_main(reg, "uv.report", {"object": "Cube"}, ctx)
    assert rep["object"] == "Cube"
    assert rep["has_uvs"] is True
    assert rep["uv_layers"] == ["UVMap", "Lightmap"]
    assert rep["uv_layer_count"] == 2
    assert rep["active_uv_layer"] == "Lightmap"  # FakeUVLayers.active = last
    assert rep["island_count"] is None  # bmesh not importable in fake env


def test_report_without_uvs(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(uv_layer_names=[])))
    reg = build_default_registry()
    rep = dispatch_on_main(reg, "uv.report", {"object": "Cube"}, ctx)
    assert rep["has_uvs"] is False
    assert rep["uv_layers"] == []
    assert rep["uv_layer_count"] == 0
    assert rep["active_uv_layer"] is None


def test_report_is_read_only_no_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(uv_layer_names=["UVMap"])))
    reg = build_default_registry()
    dispatch_on_main(reg, "uv.report", {"object": "Cube"}, ctx)
    assert bpy.undo_pushes == []


# -- UV layer management ----------------------------------------------------------


def test_router_contains_uv_layer_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"uv.layers", "uv.layer_create", "uv.layer_set_active", "uv.layer_delete"} <= names


def test_layers_reports_active_layer(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(uv_layer_names=["UVMap", "Lightmap"])))
    reg = build_default_registry()

    out = dispatch_on_main(reg, "uv.layers", {"object": "Cube"}, ctx)

    assert out == {
        "object": "Cube",
        "layers": ["UVMap", "Lightmap"],
        "count": 2,
        "active": "Lightmap",
        "active_index": 1,
    }


def test_layer_create_uses_mesh_uv_layers_new(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(uv_layer_names=["UVMap"])
    bpy.add(FakeObj("Cube", data=mesh))
    reg = build_default_registry()

    out = dispatch_on_main(reg, "uv.layer_create", {"object": "Cube", "name": "Lightmap", "do_init": False}, ctx)

    assert mesh.uv_layers.new_calls == [{"name": "Lightmap", "do_init": False}]
    assert out["layers"] == ["UVMap", "Lightmap"]
    assert out["active"] == "UVMap"
    assert bpy.undo_pushes == ["niua:uv.layer_create"]


def test_layer_set_active_by_name(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(uv_layer_names=["UVMap", "Lightmap"])
    bpy.add(FakeObj("Cube", data=mesh))
    reg = build_default_registry()

    out = dispatch_on_main(reg, "uv.layer_set_active", {"object": "Cube", "name": "UVMap"}, ctx)

    assert mesh.uv_layers.active.name == "UVMap"
    assert out["active"] == "UVMap"
    assert out["active_index"] == 0


def test_layer_delete_by_name(env) -> None:
    ctx, bpy = env
    mesh = FakeMesh(uv_layer_names=["UVMap", "Lightmap"])
    bpy.add(FakeObj("Cube", data=mesh))
    reg = build_default_registry()

    out = dispatch_on_main(reg, "uv.layer_delete", {"object": "Cube", "name": "Lightmap"}, ctx)

    assert out["layers"] == ["UVMap"]
    assert out["active"] == "UVMap"
