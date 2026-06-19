"""Context resolver unit tests (fake-bpy).

The resolver sets active object + selection, switches interaction mode (restoring it),
enters a temp_override for an editor area when available, and turns a failing operator
poll() into a clean precondition_failed error. ``bpy`` is injected into sys.modules as a
fake so the lazily-imported resolver runs without Blender.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.errors import PRECONDITION, BridgeError


class FakeObj:
    def __init__(self, name: str) -> None:
        self.name = name
        self._selected = False
        self.mode = "OBJECT"

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[])
        self._active_obj = None
        self.mode_calls: list[str] = []
        self.override_calls: list[dict] = []

        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

            @active.setter
            def active(self_inner, value):
                bpy._active_obj = value

        self._view_layer_objects = _Objects()
        self.view_layer = types.SimpleNamespace(objects=self._view_layer_objects)

        # context.object reflects the active object's mode
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
                bpy.override_calls.append(kw)
                yield

        self.context = _Context()

        class _ObjectOps:
            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        self.ops = types.SimpleNamespace(object=_ObjectOps())

    def add(self, name: str) -> FakeObj:
        obj = FakeObj(name)
        self.objects_by_name[name] = obj
        self.scene.objects.append(obj)
        return obj

    # bpy.data.objects.get(name)
    @property
    def data(self):
        store = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))

        return _Data()

    def add_area(self, area_type: str = "VIEW_3D") -> None:
        region = types.SimpleNamespace(type="WINDOW")
        area = types.SimpleNamespace(type=area_type, regions=[region])
        screen = types.SimpleNamespace(areas=[area])
        window = types.SimpleNamespace(screen=screen)
        self.context.window_manager.windows.append(window)


@pytest.fixture()
def fake_bpy(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return bpy


def test_module_importable_without_bpy() -> None:
    # The resolver module imports cleanly even with no bpy in sys.modules.
    sys.modules.pop("bpy", None)
    import importlib

    import niua_mcp_bridge.core.context as cmod

    importlib.reload(cmod)
    assert hasattr(cmod, "ensure") and hasattr(cmod, "check_poll")


def test_ensure_sets_active_and_selection_then_restores(fake_bpy) -> None:
    cube = fake_bpy.add("Cube")
    other = fake_bpy.add("Other")
    other.select_set(True)
    fake_bpy._active_obj = other

    ctx = Ctx(fake_bpy)
    with ctx.ensure(active="Cube", select=["Cube"]):
        assert fake_bpy.view_layer.objects.active is cube
        assert cube.select_get() is True
        assert other.select_get() is False

    # Restored to the pre-block state.
    assert fake_bpy.view_layer.objects.active is other
    assert other.select_get() is True
    assert cube.select_get() is False


def test_ensure_switches_mode_and_restores(fake_bpy) -> None:
    obj = fake_bpy.add("Cube")
    fake_bpy._active_obj = obj  # mode OBJECT

    ctx = Ctx(fake_bpy)
    with ctx.ensure(active="Cube", mode="edit"):
        assert obj.mode == "EDIT"
    assert obj.mode == "OBJECT"
    # Switched in, switched back.
    assert fake_bpy.mode_calls == ["EDIT", "OBJECT"]


def test_ensure_uses_temp_override_when_area_present(fake_bpy) -> None:
    fake_bpy.add("Cube")
    fake_bpy.add_area("VIEW_3D")

    ctx = Ctx(fake_bpy)
    with ctx.ensure(active="Cube", area="VIEW_3D"):
        pass
    assert len(fake_bpy.override_calls) == 1
    assert fake_bpy.override_calls[0]["area"].type == "VIEW_3D"


def test_ensure_skips_override_when_no_area(fake_bpy) -> None:
    fake_bpy.add("Cube")
    ctx = Ctx(fake_bpy)
    with ctx.ensure(active="Cube", area="VIEW_3D"):
        pass
    assert fake_bpy.override_calls == []  # headless: no area, no override, no crash


def test_ensure_unknown_object_raises_precondition(fake_bpy) -> None:
    ctx = Ctx(fake_bpy)
    with pytest.raises(BridgeError) as exc:
        with ctx.ensure(active="Ghost"):
            pass
    assert exc.value.code == PRECONDITION


def test_check_poll_raises_clean_precondition_on_false(fake_bpy) -> None:
    ctx = Ctx(fake_bpy)
    op = types.SimpleNamespace(poll=lambda: False)
    with pytest.raises(BridgeError) as exc:
        ctx.check_poll(op)
    assert exc.value.code == PRECONDITION


def test_check_poll_passes_when_true(fake_bpy) -> None:
    ctx = Ctx(fake_bpy)
    op = types.SimpleNamespace(poll=lambda: True)
    ctx.check_poll(op)  # no raise


def test_check_poll_normalizes_runtimeerror(fake_bpy) -> None:
    ctx = Ctx(fake_bpy)

    def boom():
        raise RuntimeError("context incorrect")

    op = types.SimpleNamespace(poll=boom)
    with pytest.raises(BridgeError) as exc:
        ctx.check_poll(op)
    assert exc.value.code == PRECONDITION


def test_exception_in_body_still_restores_mode(fake_bpy) -> None:
    obj = fake_bpy.add("Cube")
    fake_bpy._active_obj = obj
    ctx = Ctx(fake_bpy)
    with pytest.raises(ValueError):
        with ctx.ensure(active="Cube", mode="EDIT"):
            raise ValueError("boom")
    assert obj.mode == "OBJECT"  # restored despite the error
