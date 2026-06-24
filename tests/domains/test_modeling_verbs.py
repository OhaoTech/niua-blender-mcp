import sys
import types
import math
from contextlib import contextmanager

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class _Op:
    def __init__(self, log: list, name: str) -> None:
        self._log = log
        self._name = name

    def poll(self) -> bool:
        return True

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))


class _FakeMesh:
    pass


class _FakeObj:
    def __init__(self, name: str) -> None:
        self.name = name
        self.type = "MESH"
        self.data = _FakeMesh()
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class _FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, _FakeObj] = {}
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
            edges_select_sharp = _Op(log, "mesh.edges_select_sharp")
            bevel = _Op(log, "mesh.bevel")
            inset = _Op(log, "mesh.inset")
            tris_convert_to_quads = _Op(log, "mesh.tris_convert_to_quads")
            normals_make_consistent = _Op(log, "mesh.normals_make_consistent")
            remove_doubles = _Op(log, "mesh.remove_doubles")
            delete_loose = _Op(log, "mesh.delete_loose")

        class _ObjectOps:
            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(mesh=_MeshOps(), object=_ObjectOps(), ed=_EdOps())

    def add(self, obj: _FakeObj) -> _FakeObj:
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        store = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))

        return _Data()


def _names(log):
    return [name for name, _ in log]


def _make_bpy_with_object(monkeypatch):
    bpy = _FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    bpy.add(_FakeObj("Cube"))
    return bpy


def test_retopo_quads_runs_the_pipeline(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "model.retopo_quads", {"object": "Cube"}, Ctx(bpy))
    assert out["object"] == "Cube"
    assert out["applied"] == ["tris_convert_to_quads", "normals_make_consistent", "remove_doubles"]
    assert _names(bpy.op_calls) == [
        "mesh.select_all",
        "mesh.tris_convert_to_quads",
        "mesh.normals_make_consistent",
        "mesh.remove_doubles",
    ]
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["niua:model.retopo_quads"]


def test_bevel_edges_selects_sharp_edges_then_bevels(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(
        reg,
        "model.bevel_edges",
        {"object": "Cube", "angle": 45.0, "width": 0.03, "segments": 3},
        Ctx(bpy),
    )
    assert out == {"object": "Cube", "applied": ["edges_select_sharp", "bevel"], "segments": 3}
    assert _names(bpy.op_calls) == ["mesh.select_all", "mesh.edges_select_sharp", "mesh.bevel"]
    assert bpy.op_calls[0][1] == {"action": "DESELECT"}
    assert round(bpy.op_calls[1][1]["sharpness"], 6) == 0.785398
    assert bpy.op_calls[2][1] == {"offset": 0.03, "segments": 3, "affect": "EDGES"}
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["niua:model.bevel_edges"]


def test_bevel_edges_is_exposed_in_server_router():
    from niua_blender_mcp.domains import build_router

    specs = {s.name: s for s in build_router().specs()}
    assert "model.bevel_edges" in specs
    assert specs["model.bevel_edges"].tier == "curated"


def test_recess_panels_insets_all_faces_with_depth(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(
        reg,
        "model.recess_panels",
        {"object": "Cube", "inset": 0.08, "depth": 0.04},
        Ctx(bpy),
    )
    assert out == {
        "object": "Cube",
        "applied": ["select_all", "inset"],
        "inset": 0.08,
        "depth": 0.04,
    }
    assert _names(bpy.op_calls) == ["mesh.select_all", "mesh.inset"]
    assert bpy.op_calls[0][1] == {"action": "SELECT"}
    assert bpy.op_calls[1][1] == {"thickness": 0.08, "depth": -0.04, "use_individual": True}
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["niua:model.recess_panels"]


def test_recess_panels_is_exposed_in_server_router():
    from niua_blender_mcp.domains import build_router

    specs = {s.name: s for s in build_router().specs()}
    assert "model.recess_panels" in specs
    assert specs["model.recess_panels"].tier == "curated"


def test_panel_detail_pass_runs_hard_surface_sequence(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "hard_surface.panel_detail_pass", {"object": "Cube"}, Ctx(bpy))

    assert out["object"] == "Cube"
    assert out["asset_class"] == "hard_surface_prop"
    assert out["workflow_id"] == "hard_surface.panel_detail_pass"
    assert out["applied"] == [
        "select_all",
        "inset",
        "edges_select_sharp",
        "bevel",
        "tris_convert_to_quads",
        "normals_make_consistent",
        "remove_doubles",
    ]
    assert out["params"] == {
        "inset": 0.08,
        "depth": 0.04,
        "angle": 30.0,
        "width": 0.02,
        "segments": 2,
        "face_threshold": 40.0,
    }
    assert out["warnings"] == [
        "Re-check topology gates after the pass; beveling and inset operations can create extra poles."
    ]
    assert bpy.op_calls == [
        ("mesh.select_all", {"action": "SELECT"}),
        ("mesh.inset", {"thickness": 0.08, "depth": -0.04, "use_individual": True}),
        ("mesh.select_all", {"action": "DESELECT"}),
        ("mesh.edges_select_sharp", {"sharpness": math.radians(30.0)}),
        ("mesh.bevel", {"offset": 0.02, "segments": 2, "affect": "EDGES"}),
        (
            "mesh.select_all",
            {"action": "SELECT"},
        ),
        (
            "mesh.tris_convert_to_quads",
            {"face_threshold": math.radians(40.0), "shape_threshold": math.radians(40.0)},
        ),
        ("mesh.normals_make_consistent", {}),
        ("mesh.remove_doubles", {}),
    ]
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["niua:hard_surface.panel_detail_pass"]


def test_panel_detail_pass_is_exposed_in_server_router():
    from niua_blender_mcp.domains import build_router

    specs = {s.name: s for s in build_router().specs()}
    assert "hard_surface.panel_detail_pass" in specs
    assert specs["hard_surface.panel_detail_pass"].mutates is True
    assert specs["hard_surface.panel_detail_pass"].feedback == "viewport"
    assert specs["hard_surface.panel_detail_pass"].tier == "curated"


def test_generated_cleanup_pass_runs_available_delete_loose_sequence(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "model.generated_cleanup_pass", {"object": "Cube"}, Ctx(bpy))

    assert out["object"] == "Cube"
    assert out["asset_class"] == "generated_cleanup"
    assert out["workflow_id"] == "generated_cleanup.rebuild_noisy_mesh"
    assert out["applied"] == [
        "select_all",
        "normals_make_consistent",
        "remove_doubles",
        "delete_loose",
        "tris_convert_to_quads",
    ]
    assert out["skipped"] == []
    assert out["params"] == {"face_threshold": 35.0, "merge_distance": 0.0005}
    assert out["postcheck_recommended"] == ["feedback.topology", "pipeline.gate_check"]
    assert out["warnings"] == [
        "Generated cleanup can erase intentional tiny detail; checkpoint before running."
    ]
    assert bpy.op_calls == [
        ("mesh.select_all", {"action": "SELECT"}),
        ("mesh.normals_make_consistent", {}),
        ("mesh.remove_doubles", {"threshold": 0.0005}),
        ("mesh.delete_loose", {}),
        (
            "mesh.tris_convert_to_quads",
            {"face_threshold": math.radians(35.0), "shape_threshold": math.radians(35.0)},
        ),
    ]
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["niua:model.generated_cleanup_pass"]


def test_generated_cleanup_pass_reports_unavailable_delete_loose(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    monkeypatch.delattr(type(bpy.ops.mesh), "delete_loose")
    reg = build_default_registry()

    out = dispatch_on_main(reg, "model.generated_cleanup_pass", {"object": "Cube"}, Ctx(bpy))

    assert "delete_loose" not in out["applied"]
    assert out["skipped"] == [{"operator": "mesh.delete_loose", "reason": "unavailable"}]
    assert "mesh.delete_loose was unavailable; inspect for loose generated fragments." in out["warnings"]
    assert _names(bpy.op_calls) == [
        "mesh.select_all",
        "mesh.normals_make_consistent",
        "mesh.remove_doubles",
        "mesh.tris_convert_to_quads",
    ]


def test_generated_cleanup_pass_is_exposed_in_server_router():
    from niua_blender_mcp.domains import build_router

    specs = {s.name: s for s in build_router().specs()}
    spec = specs["model.generated_cleanup_pass"]
    assert spec.mutates is True
    assert spec.feedback == "viewport"
    assert spec.tier == "curated"
    assert spec.params["face_threshold"].default == 35.0
    assert spec.params["merge_distance"].default == 0.0005
