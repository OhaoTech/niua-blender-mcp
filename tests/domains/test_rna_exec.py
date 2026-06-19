"""rna_exec domain unit tests (fake-bpy).

Extends the FakeBpy pattern with:
- operators that expose ``get_rna_type().properties`` (so call_operator can validate
  and coerce args, drop unknown keys, and ignore POINTER/COLLECTION props), and
- a ``bpy.data`` supporting both attribute access and collection-by-name lookup (so
  set_property / get_property can resolve dotted paths like 'objects.Cube.location').

Args/values are passed to handlers as JSON-encoded strings (the chosen approach: no new
kernel param kind), so the tests json-encode them too.
"""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


# -- fake RNA --------------------------------------------------------------------


class FakeProp:
    def __init__(self, identifier, type="FLOAT", is_array=False, array_length=0) -> None:
        self.identifier = identifier
        self.type = type
        self.is_array = is_array
        self.array_length = array_length


class FakeRnaType:
    def __init__(self, props) -> None:
        self.properties = props


class _Op:
    """A callable operator with poll() and get_rna_type()."""

    def __init__(self, log, name, props=None, poll_ok=True) -> None:
        self._log = log
        self._name = name
        self._props = props or []
        self._poll_ok = poll_ok

    def poll(self) -> bool:
        return self._poll_ok

    def get_rna_type(self):
        return FakeRnaType(list(self._props) + [FakeProp("rna_type", "POINTER")])

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))


# -- fake datablocks -------------------------------------------------------------


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.location = [0.0, 0.0, 0.0]
        self.hide_viewport = False
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class _Collection:
    """A name-keyed datablock collection: supports get() and [] but not attr-by-name."""

    def __init__(self) -> None:
        self._store: dict = {}

    def add(self, obj) -> None:
        self._store[obj.name] = obj

    def get(self, name):
        return self._store.get(name)

    def __getitem__(self, name):
        return self._store[name]


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = _Collection()
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
            bevel = _Op(log, "mesh.bevel", props=[
                FakeProp("offset", "FLOAT"),
                FakeProp("segments", "INT"),
                FakeProp("affect", "ENUM"),
            ])

        class _ObjectOps:
            modifier_add = _Op(log, "object.modifier_add", props=[
                FakeProp("type", "ENUM"),
                FakeProp("object", "POINTER"),  # unsupported: should be ignored
            ])

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
        self.objects.add(obj)
        self.scene.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        objects = self.objects

        class _Data:
            pass

        d = _Data()
        d.objects = objects
        return d


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _names(log):
    return [n for n, _ in log]


# -- rna.call_operator -----------------------------------------------------------


def test_call_operator_runs_and_coerces_args(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "rna.call_operator",
        {"idname": "mesh.bevel", "args": json.dumps({"offset": 0.2, "segments": 3}), "object": "Cube", "mode": "EDIT"},
        ctx,
    )
    assert result["operator"] == "mesh.bevel"
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "mesh.bevel")
    assert kwargs["offset"] == 0.2 and isinstance(kwargs["offset"], float)
    assert kwargs["segments"] == 3 and isinstance(kwargs["segments"], int)
    assert bpy.undo_pushes == ["niua:rna.call_operator"]


def test_call_operator_drops_unknown_args(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "rna.call_operator",
        {"idname": "mesh.bevel", "args": json.dumps({"offset": 0.1, "bogus": 9})},
        ctx,
    )
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "mesh.bevel")
    assert "bogus" not in kwargs
    assert result["dropped_args"] == ["bogus"]


def test_call_operator_ignores_pointer_props_with_note(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "rna.call_operator",
        {"idname": "object.modifier_add", "args": json.dumps({"type": "SUBSURF", "object": "Other"}), "object": "Cube"},
        ctx,
    )
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "object.modifier_add")
    assert kwargs == {"type": "SUBSURF"}
    assert result["ignored_args"] == ["object"]
    assert "note" in result


def test_call_operator_unknown_operator_raises_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rna.call_operator", {"idname": "mesh.does_not_exist"}, ctx)
    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []


def test_call_operator_failing_poll_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    bpy.ops.mesh.bevel._poll_ok = False
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rna.call_operator", {"idname": "mesh.bevel", "object": "Cube"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_call_operator_bad_json_args_raises_invalid_params(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rna.call_operator", {"idname": "mesh.bevel", "args": "{not json"}, ctx)
    assert exc.value.code == INVALID_PARAMS


def test_call_operator_missing_idname_raises_invalid_params(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rna.call_operator", {}, ctx)
    assert exc.value.code == INVALID_PARAMS


def test_call_operator_select_resolves_and_runs(env) -> None:
    # The context resolver selects during the block and restores afterward, so we
    # assert the op ran (a missing select name would raise precondition before this).
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    dispatch_on_main(
        reg,
        "rna.call_operator",
        {"idname": "mesh.bevel", "object": "Cube", "select": json.dumps(["Cube"])},
        ctx,
    )
    assert "mesh.bevel" in _names(bpy.op_calls)


def test_call_operator_unknown_select_name_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "rna.call_operator",
            {"idname": "mesh.bevel", "object": "Cube", "select": json.dumps(["Ghost"])},
            ctx,
        )
    assert exc.value.code == PRECONDITION


# -- rna.get_property ------------------------------------------------------------


def test_get_property_reads_value(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    obj.location = [1.0, 2.0, 3.0]
    reg = build_default_registry()
    result = dispatch_on_main(reg, "rna.get_property", {"path": "objects.Cube.location"}, ctx)
    assert result["value"] == [1.0, 2.0, 3.0]
    assert bpy.undo_pushes == []  # read-only, no undo


def test_get_property_missing_path_raises_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rna.get_property", {"path": "objects.Ghost.location"}, ctx)
    assert exc.value.code == NOT_FOUND


# -- rna.set_property ------------------------------------------------------------


def test_set_property_assigns_and_pushes_undo(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "rna.set_property",
        {"path": "objects.Cube.location", "value": json.dumps([4, 5, 6])},
        ctx,
    )
    assert obj.location == [4, 5, 6]
    assert result["value"] == [4, 5, 6]
    assert bpy.undo_pushes == ["niua:rna.set_property"]


def test_set_property_coerces_scalar_to_existing_type(env) -> None:
    ctx, bpy = env
    obj = bpy.add(FakeObj("Cube"))
    obj.hide_viewport = False
    reg = build_default_registry()
    dispatch_on_main(reg, "rna.set_property", {"path": "objects.Cube.hide_viewport", "value": "true"}, ctx)
    assert obj.hide_viewport is True


def test_set_property_missing_value_raises_invalid_params(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rna.set_property", {"path": "objects.Cube.location"}, ctx)
    assert exc.value.code == INVALID_PARAMS


def test_set_property_unknown_attr_raises_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rna.set_property", {"path": "objects.Cube.nope", "value": "1"}, ctx)
    assert exc.value.code == NOT_FOUND
