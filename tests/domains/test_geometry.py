from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import PRECONDITION, BridgeError


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


class FakeTextData(FakeData):
    def __init__(self, name: str) -> None:
        super().__init__(name, splines=[])
        self.body = "Text"
        self.align_x = "LEFT"
        self.align_y = "TOP_BASELINE"
        self.size = 1.0
        self.space_line = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.dimensions = "2D"
        self.fill_mode = "BOTH"


class FakeMetaElement:
    def __init__(self, element_type: str) -> None:
        self.type = element_type


class FakeMetaData:
    def __init__(self, element_type: str) -> None:
        self.name = "MetaData"
        self.materials = []
        self.elements = [FakeMetaElement(element_type)]


class FakeLayer:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeGreaseData:
    def __init__(self) -> None:
        self.name = "GreaseData"
        self.materials = [object()]
        self.layers = [FakeLayer("Layer")]


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

            def primitive_nurbs_curve_add(self, **kwargs):
                bpy.op_calls.append(("curve.primitive_nurbs_curve_add", kwargs))
                obj = FakeObject("NurbsCurve", data=FakeData("NurbsCurve", splines=[FakeSpline("NURBS", points=5)]))
                obj.location = list(kwargs.get("location", [0, 0, 0]))
                obj.rotation_euler = list(kwargs.get("rotation", [0, 0, 0]))
                obj.scale = list(kwargs.get("scale", [1, 1, 1]))
                bpy.add(obj)

        class ObjectOps:
            def text_add(self, **kwargs):
                bpy.op_calls.append(("object.text_add", kwargs))
                obj = FakeObject("Text", obj_type="FONT", data=FakeTextData("TextData"))
                obj.location = list(kwargs.get("location", [0, 0, 0]))
                obj.rotation_euler = list(kwargs.get("rotation", [0, 0, 0]))
                obj.scale = list(kwargs.get("scale", [1, 1, 1]))
                bpy.add(obj)

            def metaball_add(self, **kwargs):
                bpy.op_calls.append(("object.metaball_add", kwargs))
                obj = FakeObject("Mball", obj_type="META", data=FakeMetaData(kwargs.get("type", "BALL")))
                obj.location = list(kwargs.get("location", [0, 0, 0]))
                obj.rotation_euler = list(kwargs.get("rotation", [0, 0, 0]))
                obj.scale = list(kwargs.get("scale", [1, 1, 1]))
                bpy.add(obj)

            def grease_pencil_add(self, **kwargs):
                bpy.op_calls.append(("object.grease_pencil_add", kwargs))
                obj = FakeObject("GPencil", obj_type="GREASEPENCIL", data=FakeGreaseData())
                obj.location = list(kwargs.get("location", [0, 0, 0]))
                obj.rotation_euler = list(kwargs.get("rotation", [0, 0, 0]))
                obj.scale = list(kwargs.get("scale", [1, 1, 1]))
                obj.show_in_front = bool(kwargs.get("use_in_front", False))
                bpy.add(obj)

            def mode_set(self, mode="OBJECT", **kwargs):
                bpy.mode_calls.append(mode)
                active = bpy.context.view_layer.objects.active
                if active is not None:
                    active.mode = mode

        class SurfaceOps:
            def primitive_nurbs_surface_surface_add(self, **kwargs):
                bpy.op_calls.append(("surface.primitive_nurbs_surface_surface_add", kwargs))
                obj = FakeObject("SurfPatch", obj_type="SURFACE", data=FakeData("SurfData", splines=[FakeSpline("NURBS", points=16)]))
                obj.location = list(kwargs.get("location", [0, 0, 0]))
                obj.rotation_euler = list(kwargs.get("rotation", [0, 0, 0]))
                obj.scale = list(kwargs.get("scale", [1, 1, 1]))
                bpy.add(obj)

        class EdOps:
            def undo_push(self, message="", **kwargs):
                bpy.op_calls.append(("ed.undo_push", {"message": message, **kwargs}))

        return types.SimpleNamespace(curve=CurveOps(), object=ObjectOps(), surface=SurfaceOps(), ed=EdOps())


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


def test_router_contains_non_mesh_creation_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "geometry.create_text",
        "geometry.create_surface",
        "geometry.create_metaball",
        "geometry.create_grease_pencil",
    } <= names


def test_create_text_sets_text_fields(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry.create_text",
        {
            "name": "Label",
            "body": "Hello",
            "align_x": "CENTER",
            "align_y": "CENTER",
            "size": 2.5,
            "location": [1, 0, 0],
        },
        ctx,
    )

    assert out["name"] == "Label"
    assert out["type"] == "FONT"
    assert out["text"]["body"] == "Hello"
    assert out["text"]["align_x"] == "CENTER"
    assert out["text"]["align_y"] == "CENTER"
    assert out["text"]["size"] == 2.5
    assert bpy.op_calls[0][0] == "object.text_add"


def test_create_surface_metaball_and_grease_pencil(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    reg = build_default_registry()

    surface = dispatch_on_main(
        reg,
        "geometry.create_surface",
        {"type": "SURFACE", "name": "Patch", "radius": 1.5},
        ctx,
    )
    metaball = dispatch_on_main(
        reg,
        "geometry.create_metaball",
        {"type": "CAPSULE", "name": "Blob", "radius": 0.75},
        ctx,
    )
    grease = dispatch_on_main(
        reg,
        "geometry.create_grease_pencil",
        {"type": "EMPTY", "name": "Sketch", "radius": 1.0, "use_in_front": True},
        ctx,
    )

    assert surface["name"] == "Patch"
    assert surface["type"] == "SURFACE"
    assert surface["splines"] == [{"type": "NURBS", "bezier_points": 0, "points": 16}]
    assert metaball["name"] == "Blob"
    assert metaball["type"] == "META"
    assert metaball["metaball"] == {"elements": 1, "types": ["CAPSULE"]}
    assert grease["name"] == "Sketch"
    assert grease["type"] == "GREASEPENCIL"
    assert grease["grease_pencil"] == {"layers": 1, "names": ["Layer"]}
    assert ("surface.primitive_nurbs_surface_surface_add", {
        "radius": 1.5,
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }) in bpy.op_calls
    assert ("object.metaball_add", {
        "type": "CAPSULE",
        "radius": 0.75,
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }) in bpy.op_calls
    assert ("object.grease_pencil_add", {
        "type": "EMPTY",
        "radius": 1.0,
        "use_in_front": True,
        "location": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }) in bpy.op_calls


def test_router_contains_geometry_setters() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"geometry.set_curve", "geometry.set_text"} <= names


def test_set_curve_updates_only_provided_fields(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    data = FakeData("CurveData")
    data.bevel_resolution = 7
    bpy.add(FakeObject("CurveHero", data=data))
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry.set_curve",
        {
            "object": "CurveHero",
            "bevel_depth": 0.25,
            "extrude": 0.5,
            "resolution_u": 24,
            "dimensions": "2D",
            "use_fill_caps": True,
        },
        ctx,
    )

    assert data.bevel_depth == 0.25
    assert data.extrude == 0.5
    assert data.resolution_u == 24
    assert data.dimensions == "2D"
    assert data.use_fill_caps is True
    assert data.bevel_resolution == 7
    assert out["curve"]["bevel_depth"] == 0.25


def test_set_curve_rejects_unsupported_object_type(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("Blob", obj_type="META", data=FakeMetaData("BALL")))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "geometry.set_curve", {"object": "Blob", "bevel_depth": 0.1}, ctx)
    assert exc.value.code == PRECONDITION


def test_set_text_updates_only_provided_fields(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    data = FakeTextData("TextData")
    data.align_y = "TOP"
    bpy.add(FakeObject("Label", obj_type="FONT", data=data))
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry.set_text",
        {
            "object": "Label",
            "body": "Updated",
            "align_x": "RIGHT",
            "size": 3.0,
            "offset_x": 0.25,
        },
        ctx,
    )

    assert data.body == "Updated"
    assert data.align_x == "RIGHT"
    assert data.align_y == "TOP"
    assert data.size == 3.0
    assert data.offset_x == 0.25
    assert out["text"]["body"] == "Updated"


def test_set_text_rejects_non_text_object(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("CurveHero", data=FakeData("CurveData")))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "geometry.set_text", {"object": "CurveHero", "body": "Nope"}, ctx)
    assert exc.value.code == PRECONDITION
