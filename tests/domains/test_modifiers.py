"""Modifiers domain unit tests (fake-bpy).

Extends the FakeBpy pattern from tests/test_dispatch.py / test_mesh.py with a
``modifiers`` collection on objects (a ``.new()``/``.get()``/iterable wrapper that
mimics ``bpy.types.bpy_prop_collection``) plus the ``object.modifier_apply`` /
``object.modifier_remove`` operators the apply/remove handlers call. Operators are
callable AND carry a ``poll`` attribute so ctx.check_poll passes. ``bpy`` is injected
into sys.modules so the lazily-imported context resolver runs against the same fake.
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
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


class FakeModifier:
    """Minimal stand-in for a Blender modifier datablock."""

    def __init__(self, name: str, type: str) -> None:
        self.name = name
        self.type = type
        self.show_viewport = True
        self.show_render = True
        self.show_in_editmode = False
        self.show_on_cage = False
        self.show_expanded = True
        self.is_active = False
        self.execution_time = 0.0
        self.node_group = None
        # A spread of property types so _coerce_value has something to coerce.
        self.levels = 1  # int (SUBSURF)
        self.thickness = 0.01  # float (SOLIDIFY)
        self.use_clip = False  # bool (MIRROR)


class FakeModifierStack:
    """Mimics obj.modifiers: .new(), .get(), iteration, len()."""

    def __init__(self) -> None:
        self._items: list[FakeModifier] = []

    def new(self, name: str, type: str) -> FakeModifier:
        mod = FakeModifier(name, type)
        self._items.append(mod)
        return mod

    def get(self, name: str) -> FakeModifier | None:
        return next((m for m in self._items if m.name == name), None)

    def remove(self, mod: FakeModifier) -> None:
        self._items.remove(mod)

    def move_to_index(self, mod: FakeModifier, index: int) -> None:
        self._items.remove(mod)
        self._items.insert(max(0, min(index, len(self._items))), mod)

    def copy(self, mod: FakeModifier) -> FakeModifier:
        copy = FakeModifier(f"{mod.name}.001", mod.type)
        for key, value in vars(mod).items():
            if key not in {"name"}:
                setattr(copy, key, value)
        self._items.append(copy)
        return copy

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.modifiers = FakeModifierStack()
        self._selected = False
        self.mode = "OBJECT"

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class _Op:
    """A callable operator that records calls and polls True by default.

    ``object.modifier_apply``/``modifier_remove`` mutate the bound stack so list/
    state reflects the change, mirroring real bpy.ops behavior.
    """

    def __init__(self, log: list, name: str, bpy, poll_ok: bool = True) -> None:
        self._log = log
        self._name = name
        self._bpy = bpy
        self._poll_ok = poll_ok

    def poll(self) -> bool:
        return self._poll_ok

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))
        if self._name in ("object.modifier_apply", "object.modifier_remove"):
            obj = self._bpy._active_obj
            mod = obj.modifiers.get(kwargs.get("modifier", "")) if obj else None
            if mod is not None:
                obj.modifiers.remove(mod)
        elif self._name == "object.modifier_move_to_index":
            obj = self._bpy._active_obj
            mod = obj.modifiers.get(kwargs.get("modifier", "")) if obj else None
            if mod is not None:
                obj.modifiers.move_to_index(mod, int(kwargs.get("index", 0)))
        elif self._name == "object.modifier_copy":
            obj = self._bpy._active_obj
            mod = obj.modifiers.get(kwargs.get("modifier", "")) if obj else None
            if mod is not None:
                obj.modifiers.copy(mod)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active_obj = None
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []
        self.types = types.SimpleNamespace(
            Modifier=types.SimpleNamespace(
                bl_rna=types.SimpleNamespace(
                    properties={
                        "type": types.SimpleNamespace(
                            enum_items=[
                                types.SimpleNamespace(identifier="SUBSURF", name="Subdivision Surface"),
                                types.SimpleNamespace(identifier="TRIANGULATE", name="Triangulate"),
                                types.SimpleNamespace(identifier="NODES", name="Geometry Nodes"),
                            ]
                        )
                    }
                )
            )
        )

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

        class _ObjectOps:
            modifier_apply = _Op(log, "object.modifier_apply", bpy)
            modifier_remove = _Op(log, "object.modifier_remove", bpy)
            modifier_move_to_index = _Op(log, "object.modifier_move_to_index", bpy)
            modifier_copy = _Op(log, "object.modifier_copy", bpy)

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

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))
            materials: dict = {}

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _names(log):
    return [n for n, _ in log]


# -- add ---------------------------------------------------------------------------


def test_router_contains_modifier_type_tool() -> None:
    router = build_router()
    names = {spec.name for spec in router.specs()}
    assert "modifiers.types" in names
    assert router.get("modifiers.add").params["type"].kind == "string"


def test_types_reports_live_modifier_enum(env) -> None:
    ctx, _bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "modifiers.types", {}, ctx)

    assert out == {
        "types": [
            {"identifier": "SUBSURF", "name": "Subdivision Surface"},
            {"identifier": "TRIANGULATE", "name": "Triangulate"},
            {"identifier": "NODES", "name": "Geometry Nodes"},
        ]
    }


def test_add_creates_modifier_and_pushes_one_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "modifiers.add", {"object": "Cube", "type": "SUBSURF"}, ctx)
    assert result == {"object": "Cube", "modifier": "SUBSURF", "type": "SUBSURF"}
    assert len(bpy.objects_by_name["Cube"].modifiers) == 1
    assert bpy.undo_pushes == ["niua:modifiers.add"]


def test_add_uses_custom_name(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "modifiers.add", {"object": "Cube", "type": "BEVEL", "name": "MyBevel"}, ctx
    )
    assert result["modifier"] == "MyBevel"
    assert bpy.objects_by_name["Cube"].modifiers.get("MyBevel") is not None


def test_add_accepts_live_modifier_type_not_static_allowlist(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()

    result = dispatch_on_main(reg, "modifiers.add", {"object": "Cube", "type": "TRIANGULATE"}, ctx)

    assert result == {"object": "Cube", "modifier": "TRIANGULATE", "type": "TRIANGULATE"}
    assert bpy.objects_by_name["Cube"].modifiers.get("TRIANGULATE") is not None


def test_add_defaults_to_active_object(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))  # becomes active
    reg = build_default_registry()
    result = dispatch_on_main(reg, "modifiers.add", {"type": "MIRROR"}, ctx)
    assert result["object"] == "Cube"


# -- set ---------------------------------------------------------------------------


def test_set_int_property_coerces_from_string(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Subsurf", type="SUBSURF")
    bpy.add(obj)
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "modifiers.set",
        {"object": "Cube", "name": "Subsurf", "property": "levels", "value": "3"},
        ctx,
    )
    assert result["value"] == 3
    assert obj.modifiers.get("Subsurf").levels == 3
    assert bpy.undo_pushes == ["niua:modifiers.set"]


def test_set_float_property_coerces(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Solid", type="SOLIDIFY")
    bpy.add(obj)
    reg = build_default_registry()
    dispatch_on_main(
        reg,
        "modifiers.set",
        {"object": "Cube", "name": "Solid", "property": "thickness", "value": "0.25"},
        ctx,
    )
    assert obj.modifiers.get("Solid").thickness == 0.25


def test_set_bool_property_coerces(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Mir", type="MIRROR")
    bpy.add(obj)
    reg = build_default_registry()
    dispatch_on_main(
        reg,
        "modifiers.set",
        {"object": "Cube", "name": "Mir", "property": "use_clip", "value": "true"},
        ctx,
    )
    assert obj.modifiers.get("Mir").use_clip is True


def test_set_unknown_property_raises_invalid_params(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Subsurf", type="SUBSURF")
    bpy.add(obj)
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "modifiers.set",
            {"object": "Cube", "name": "Subsurf", "property": "nope", "value": "1"},
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []


def test_set_bad_int_value_raises_invalid_params(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Subsurf", type="SUBSURF")
    bpy.add(obj)
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "modifiers.set",
            {"object": "Cube", "name": "Subsurf", "property": "levels", "value": "abc"},
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS


def test_set_missing_modifier_raises_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "modifiers.set",
            {"object": "Cube", "name": "Ghost", "property": "levels", "value": "1"},
            ctx,
        )
    assert exc.value.code == NOT_FOUND


def test_router_contains_modifier_stack_controls() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"modifiers.set_visibility", "modifiers.move", "modifiers.copy"} <= names


def test_set_visibility_writes_only_provided_flags(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    mod = obj.modifiers.new(name="Bev", type="BEVEL")
    mod.show_render = True
    mod.show_in_editmode = False
    bpy.add(obj)
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "modifiers.set_visibility",
        {"object": "Cube", "name": "Bev", "viewport": False, "editmode": True, "expanded": False},
        ctx,
    )

    assert mod.show_viewport is False
    assert mod.show_render is True
    assert mod.show_in_editmode is True
    assert mod.show_expanded is False
    assert result["modifier"]["show_viewport"] is False
    assert result["modifier"]["show_render"] is True
    assert bpy.undo_pushes == ["niua:modifiers.set_visibility"]


def test_move_runs_operator_and_reorders_stack(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.mode = "EDIT"
    obj.modifiers.new(name="A", type="BEVEL")
    obj.modifiers.new(name="B", type="SOLIDIFY")
    obj.modifiers.new(name="C", type="TRIANGULATE")
    bpy.add(obj)
    reg = build_default_registry()

    result = dispatch_on_main(reg, "modifiers.move", {"object": "Cube", "name": "C", "index": 0}, ctx)

    assert [m.name for m in obj.modifiers] == ["C", "A", "B"]
    assert result["modifier"]["name"] == "C"
    assert result["modifier"]["index"] == 0
    assert ("object.modifier_move_to_index", {"modifier": "C", "index": 0}) in bpy.op_calls
    assert bpy.mode_calls == ["OBJECT", "EDIT"]
    assert bpy.undo_pushes == ["niua:modifiers.move"]


def test_copy_runs_operator_and_renames_copy(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Bev", type="BEVEL")
    bpy.add(obj)
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "modifiers.copy",
        {"object": "Cube", "name": "Bev", "new_name": "BevCopy"},
        ctx,
    )

    assert [m.name for m in obj.modifiers] == ["Bev", "BevCopy"]
    assert result["modifier"]["name"] == "BevCopy"
    assert result["modifier"]["type"] == "BEVEL"
    assert ("object.modifier_copy", {"modifier": "Bev"}) in bpy.op_calls
    assert bpy.undo_pushes == ["niua:modifiers.copy"]


# -- apply -------------------------------------------------------------------------


def test_apply_runs_object_op_and_object_mode(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.mode = "EDIT"  # force a real mode switch so mode_calls is populated
    obj.modifiers.new(name="Subsurf", type="SUBSURF")
    bpy.add(obj)
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "modifiers.apply", {"object": "Cube", "name": "Subsurf"}, ctx
    )
    assert result == {"object": "Cube", "modifier": "Subsurf", "applied": True}
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "object.modifier_apply")
    assert kwargs == {"modifier": "Subsurf"}
    assert bpy.mode_calls[0] == "OBJECT"  # ensured OBJECT mode
    assert bpy.undo_pushes == ["niua:modifiers.apply"]
    assert len(obj.modifiers) == 0  # op consumed the modifier


def test_apply_missing_modifier_raises_not_found_before_op(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "modifiers.apply", {"object": "Cube", "name": "Ghost"}, ctx)
    assert exc.value.code == NOT_FOUND
    assert "object.modifier_apply" not in _names(bpy.op_calls)
    assert bpy.undo_pushes == []


def test_apply_failing_poll_raises_clean_precondition(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Subsurf", type="SUBSURF")
    bpy.add(obj)
    bpy.ops.object.modifier_apply._poll_ok = False
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "modifiers.apply", {"object": "Cube", "name": "Subsurf"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


# -- remove ------------------------------------------------------------------------


def test_remove_runs_object_op(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Bev", type="BEVEL")
    bpy.add(obj)
    reg = build_default_registry()
    result = dispatch_on_main(reg, "modifiers.remove", {"object": "Cube", "name": "Bev"}, ctx)
    assert result == {"object": "Cube", "modifier": "Bev", "removed": True}
    assert "object.modifier_remove" in _names(bpy.op_calls)
    assert len(obj.modifiers) == 0
    assert bpy.undo_pushes == ["niua:modifiers.remove"]


def test_remove_missing_modifier_raises_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "modifiers.remove", {"object": "Cube", "name": "Ghost"}, ctx)
    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []


# -- list (read-only) --------------------------------------------------------------


def test_list_returns_stack(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    obj.modifiers.new(name="Subsurf", type="SUBSURF")
    obj.modifiers.new(name="Bev", type="BEVEL")
    bpy.add(obj)
    reg = build_default_registry()
    result = dispatch_on_main(reg, "modifiers.list", {"object": "Cube"}, ctx)
    assert result["object"] == "Cube"
    assert [m["name"] for m in result["modifiers"]] == ["Subsurf", "Bev"]
    assert [m["type"] for m in result["modifiers"]] == ["SUBSURF", "BEVEL"]


def test_list_returns_rich_stack_report(env) -> None:
    ctx, bpy = env
    obj = FakeObj("Cube")
    subsurf = obj.modifiers.new(name="Subsurf", type="SUBSURF")
    subsurf.show_render = False
    nodes = obj.modifiers.new(name="Nodes", type="NODES")
    nodes.node_group = types.SimpleNamespace(name="GeoNodes")
    bpy.add(obj)
    reg = build_default_registry()

    result = dispatch_on_main(reg, "modifiers.list", {"object": "Cube"}, ctx)

    first, second = result["modifiers"]
    assert first["index"] == 0
    assert first["show_viewport"] is True
    assert first["show_render"] is False
    assert first["show_in_editmode"] is False
    assert first["show_on_cage"] is False
    assert first["show_expanded"] is True
    assert first["execution_time"] == 0.0
    assert first["properties"]["levels"] == 1
    assert first["properties"]["use_clip"] is False
    assert second["index"] == 1
    assert second["node_group"] == "GeoNodes"


def test_list_is_read_only_no_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "modifiers.list", {"object": "Cube"}, ctx)
    assert result["modifiers"] == []
    assert bpy.undo_pushes == []


# -- shared precondition handling --------------------------------------------------


def test_missing_object_raises_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "modifiers.list", {"object": "Ghost"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_no_active_object_raises_precondition(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "modifiers.add", {"type": "SUBSURF"}, ctx)
    assert exc.value.code == PRECONDITION
