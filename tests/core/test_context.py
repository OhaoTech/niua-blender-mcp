"""Regression tests for ResolvedContext restoring state after the wrapped operator removes objects
(object.join / object.delete free datablocks -- restoring by name must skip the gone ones, never
touch a freed StructRNA)."""

from niua_mcp_bridge.core.context import ResolvedContext


class _Dead:
    """An object whose datablock was freed: reading .name raises, like a removed bpy StructRNA."""

    @property
    def name(self):
        raise ReferenceError("StructRNA of type Object has been removed")


class _Live:
    def __init__(self, name):
        self.name = name
        self.selected = False

    def select_get(self):
        return self.selected

    def select_set(self, value):
        self.selected = bool(value)


class _Objects(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def _fake_bpy(objects):
    class _Scene:
        pass

    class _ViewLayer:
        pass

    class _Ctx:
        pass

    class _Data:
        pass

    class _Bpy:
        pass

    scene = _Scene()
    scene.objects = list(objects.values())
    vl = _ViewLayer()
    vl.objects = _Objects(objects)
    ctx = _Ctx()
    ctx.scene = scene
    ctx.view_layer = vl
    data = _Data()
    data.objects = _Objects(objects)
    bpy = _Bpy()
    bpy.context = ctx
    bpy.data = data
    return bpy


def test_set_selection_accepts_names_and_skips_dead_refs():
    a, b = _Live("A"), _Live("B")
    bpy = _fake_bpy({"A": a, "B": b})
    rc = ResolvedContext()
    # snapshot mixes a name (restore path) and a freed datablock -> must not raise; selects only "A"
    rc._set_selection(bpy, ["A", _Dead()])
    assert a.selected is True
    assert b.selected is False


def test_set_active_by_name_skips_missing():
    a = _Live("A")
    bpy = _fake_bpy({"A": a})
    rc = ResolvedContext()
    rc._set_active(bpy, "A")
    assert bpy.context.view_layer.objects.active is a
    # a name that no longer resolves (removed) is skipped, not assigned
    rc._set_active(bpy, "GONE")
    assert bpy.context.view_layer.objects.active is a
