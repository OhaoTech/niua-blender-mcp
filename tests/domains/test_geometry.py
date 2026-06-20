from __future__ import annotations

import sys
import types

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class _NamedList(list):
    def get(self, name: str):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class FakeSpline:
    def __init__(self, spline_type: str, bezier=0, points=0) -> None:
        self.type = spline_type
        self.bezier_points = [object() for _ in range(bezier)]
        self.points = [object() for _ in range(points)]


class FakeData:
    def __init__(self, name: str, *, splines=None) -> None:
        self.name = name
        self.bevel_depth = 0.0
        self.bevel_resolution = 4
        self.extrude = 0.0
        self.resolution_u = 12
        self.render_resolution_u = 0
        self.dimensions = "3D"
        self.fill_mode = "FULL"
        self.use_fill_caps = False
        self.materials = []
        self.splines = splines or []


class FakeObject:
    def __init__(self, name: str, obj_type: str = "CURVE", data=None) -> None:
        self.name = name
        self.type = obj_type
        self.data = data if data is not None else FakeData(f"{name}Data")
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeObjects(_NamedList):
    def add(self, obj):
        base = obj.name
        name = base
        index = 1
        while self.get(name) is not None:
            name = f"{base}.{index:03d}"
            index += 1
        obj.name = name
        self.append(obj)
        return obj


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = FakeObjects()
        self.op_calls = []
        self.mode_calls = []
        self.context = types.SimpleNamespace(
            scene=types.SimpleNamespace(objects=self.objects),
            object=None,
            view_layer=types.SimpleNamespace(objects=types.SimpleNamespace(active=None)),
            window_manager=types.SimpleNamespace(windows=[]),
        )
        self.data = types.SimpleNamespace(objects=self.objects)
        self.ops = self._make_ops()

    def add(self, obj):
        self.objects.add(obj)
        self.context.object = obj
        self.context.view_layer.objects.active = obj
        return obj

    def _make_ops(self):
        bpy = self

        class CurveOps:
            def primitive_bezier_curve_add(self, **kwargs):
                bpy.op_calls.append(("curve.primitive_bezier_curve_add", kwargs))
                obj = FakeObject("BezierCurve", data=FakeData("BezierCurve", splines=[FakeSpline("BEZIER", bezier=2)]))
                obj.location = list(kwargs.get("location", [0, 0, 0]))
                obj.rotation_euler = list(kwargs.get("rotation", [0, 0, 0]))
                obj.scale = list(kwargs.get("scale", [1, 1, 1]))
                bpy.add(obj)

            def primitive_bezier_circle_add(self, **kwargs):
                bpy.op_calls.append(("curve.primitive_bezier_circle_add", kwargs))
                obj = FakeObject("BezierCircle", data=FakeData("BezierCircle", splines=[FakeSpline("BEZIER", bezier=4)]))
                obj.location = list(kwargs.get("location", [0, 0, 0]))
                obj.rotation_euler = list(kwargs.get("rotation", [0, 0, 0]))
                obj.scale = list(kwargs.get("scale", [1, 1, 1]))
                bpy.add(obj)

        class ObjectOps:
            def mode_set(self, mode="OBJECT", **kwargs):
                bpy.mode_calls.append(mode)
                active = bpy.context.view_layer.objects.active
                if active is not None:
                    active.mode = mode

        class EdOps:
            def undo_push(self, message="", **kwargs):
                bpy.op_calls.append(("ed.undo_push", {"message": message, **kwargs}))

        return types.SimpleNamespace(curve=CurveOps(), object=ObjectOps(), ed=EdOps())


def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_geometry_curve_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"geometry.report", "geometry.create_curve"} <= names


def test_report_curve_object(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    data = FakeData("CurveData", splines=[FakeSpline("BEZIER", bezier=2), FakeSpline("NURBS", points=5)])
    data.bevel_depth = 0.12
    data.extrude = 0.5
    bpy.add(FakeObject("CurveHero", data=data))
    reg = build_default_registry()

    out = dispatch_on_main(reg, "geometry.report", {"object": "CurveHero"}, ctx)

    assert out["name"] == "CurveHero"
    assert out["type"] == "CURVE"
    assert out["data_type"] == "FakeData"
    assert out["curve"]["bevel_depth"] == 0.12
    assert out["curve"]["extrude"] == 0.5
    assert out["splines"] == [
        {"type": "BEZIER", "bezier_points": 2, "points": 0},
        {"type": "NURBS", "bezier_points": 0, "points": 5},
    ]


def test_create_curve_dispatches_operator_and_reports(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry.create_curve",
        {
            "type": "BEZIER_CIRCLE",
            "name": "CurveCircle",
            "radius": 2.0,
            "location": [1, 2, 3],
            "rotation": [0.1, 0.2, 0.3],
            "scale": [2, 2, 2],
        },
        ctx,
    )

    assert out["name"] == "CurveCircle"
    assert out["type"] == "CURVE"
    assert bpy.data.objects.get("CurveCircle") is not None
    assert bpy.op_calls[0] == (
        "curve.primitive_bezier_circle_add",
        {
            "radius": 2.0,
            "location": [1.0, 2.0, 3.0],
            "rotation": [0.1, 0.2, 0.3],
            "scale": [2.0, 2.0, 2.0],
        },
    )
