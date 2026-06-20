import sys
import types
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
            tris_convert_to_quads = _Op(log, "mesh.tris_convert_to_quads")
            normals_make_consistent = _Op(log, "mesh.normals_make_consistent")
            remove_doubles = _Op(log, "mesh.remove_doubles")

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
