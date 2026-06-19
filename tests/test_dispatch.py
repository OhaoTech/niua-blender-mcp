from __future__ import annotations

import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import Command, dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import (
    HANDLER_ERROR,
    PYTHON_DISABLED,
    UNKNOWN_TOOL,
    BridgeError,
)


class FakeObject:
    def __init__(self, name: str, type: str = "MESH", location=(0, 0, 0)) -> None:
        self._name = name
        self._bpy = None
        self.type = type
        self.location = list(location)
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.hide_viewport = False

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        old = self._name
        self._name = value
        # mimic Blender: renaming re-keys bpy.data.objects live
        if self._bpy is not None and old in self._bpy.data.objects:
            del self._bpy.data.objects[old]
            self._bpy.data.objects[value] = self

    def select_set(self, value: bool) -> None:  # pragma: no cover
        pass


class FakeBpy:
    def __init__(self) -> None:
        self.data = types.SimpleNamespace(objects={}, materials={})
        self.scene = types.SimpleNamespace(name="Scene", objects=[])
        self.context = types.SimpleNamespace(scene=self.scene, object=None)
        self.app = types.SimpleNamespace(version_string="4.4.0")
        self.undo_pushes: list[str] = []
        self.undo_calls = 0
        self.ops = self._make_ops()

    def _add(self, obj: FakeObject) -> None:
        obj._bpy = self
        base, name, i = obj._name, obj._name, 1
        while name in self.data.objects:  # mimic Blender auto-rename
            name = f"{base}.{i:03d}"
            i += 1
        obj._name = name
        self.data.objects[name] = obj
        self.scene.objects.append(obj)
        self.context.object = obj

    def _make_ops(self):
        bpy = self

        class Mesh:
            def primitive_cube_add(self, **kw):
                bpy._add(FakeObject("Cube", location=kw.get("location", (0, 0, 0))))

            def primitive_uv_sphere_add(self, **kw):
                bpy._add(FakeObject("Sphere", location=kw.get("location", (0, 0, 0))))

            def primitive_plane_add(self, **kw):
                bpy._add(FakeObject("Plane", location=kw.get("location", (0, 0, 0))))

            def primitive_cylinder_add(self, **kw):
                bpy._add(FakeObject("Cylinder", location=kw.get("location", (0, 0, 0))))

            def primitive_cone_add(self, **kw):
                bpy._add(FakeObject("Cone", location=kw.get("location", (0, 0, 0))))

        class ObjectOps:
            def empty_add(self, **kw):
                bpy._add(FakeObject("Empty", type="EMPTY", location=kw.get("location", (0, 0, 0))))

        class Ed:
            def undo_push(self, message: str = "") -> None:
                bpy.undo_pushes.append(message)

            def undo(self) -> None:
                bpy.undo_calls += 1

        return types.SimpleNamespace(mesh=Mesh(), object=ObjectOps(), ed=Ed())


def ctx(allow_python: bool = False) -> tuple[Ctx, FakeBpy]:
    bpy = FakeBpy()
    return Ctx(bpy, allow_python=allow_python), bpy


def test_create_object_creates_and_pushes_one_undo_step() -> None:
    c, bpy = ctx()
    reg = build_default_registry()
    result = dispatch_on_main(reg, "scene.create_object", {"type": "CUBE", "name": "Hero"}, c)
    assert result["name"] == "Hero"
    assert bpy.data.objects["Hero"].location == [0.0, 0.0, 0.0]
    assert bpy.undo_pushes == ["niua:scene.create_object"]
    assert bpy.undo_calls == 0


def test_set_transform_updates_object() -> None:
    c, bpy = ctx()
    reg = build_default_registry()
    dispatch_on_main(reg, "scene.create_object", {"type": "CUBE", "name": "Hero"}, c)
    result = dispatch_on_main(
        reg, "scene.set_transform", {"object": "Hero", "location": [1, 2, 3], "scale": [2, 2, 2]}, c
    )
    assert result["location"] == [1.0, 2.0, 3.0]
    assert result["scale"] == [2.0, 2.0, 2.0]


def test_scene_info_is_read_only_no_undo() -> None:
    c, bpy = ctx()
    reg = build_default_registry()
    dispatch_on_main(reg, "scene.create_object", {"type": "SPHERE", "name": "Ball"}, c)
    bpy.undo_pushes.clear()
    info = dispatch_on_main(reg, "scene.info", {}, c)
    assert info["scene"] == "Scene"
    assert any(o["name"] == "Ball" for o in info["objects"])
    assert bpy.undo_pushes == []  # reads never push undo


def test_failing_mutation_rolls_back() -> None:
    c, bpy = ctx()
    reg = build_default_registry()

    def boom(ctx_, payload):
        ctx_.bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))  # partial mutation
        raise ValueError("kaboom")

    reg.register(Command("test.boom", boom, mutates=True))
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "test.boom", {}, c)
    assert exc.value.code == HANDLER_ERROR
    assert bpy.undo_calls == 1  # rolled back


def test_unknown_command_raises() -> None:
    c, _ = ctx()
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "nope.nope", {}, c)
    assert exc.value.code == UNKNOWN_TOOL


def test_execute_python_gated_off_by_default() -> None:
    c, _ = ctx(allow_python=False)
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "system.execute_python", {"code": "1+1"}, c)
    assert exc.value.code == PYTHON_DISABLED


def test_execute_python_runs_when_enabled() -> None:
    c, bpy = ctx(allow_python=True)
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "system.execute_python", {"code": "bpy.ops.mesh.primitive_cube_add(location=(0,0,0))"}, c
    )
    assert result == {"ok": True}
    assert len(bpy.scene.objects) == 1
