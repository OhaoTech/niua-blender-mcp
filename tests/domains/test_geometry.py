from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, PRECONDITION, BridgeError


class _NamedList(list):
    def get(self, name: str):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class FakeBezierPoint:
    def __init__(self) -> None:
        self.co = [0.0, 0.0, 0.0]
        self.handle_left = [0.0, 0.0, 0.0]
        self.handle_right = [0.0, 0.0, 0.0]
        self.handle_left_type = "AUTO"
        self.handle_right_type = "AUTO"


class FakeBezierPoints(list):
    def add(self, count: int = 1) -> None:
        for _ in range(int(count)):
            self.append(FakeBezierPoint())


class FakeSpline:
    def __init__(self, spline_type: str, bezier=0, points=0) -> None:
        self.type = spline_type
        self.use_cyclic_u = False
        self.bezier_points = FakeBezierPoints(FakeBezierPoint() for _ in range(bezier))
        self.points = [object() for _ in range(points)]


class FakeSplines(list):
    def new(self, spline_type: str):
        spline = FakeSpline(spline_type, bezier=1 if spline_type == "BEZIER" else 0)
        self.append(spline)
        return spline

    def remove(self, spline) -> None:
        self[:] = [item for item in self if item is not spline]


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
        self.splines = FakeSplines(splines or [])


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


class FakeMeshData:
    def __init__(self, name: str) -> None:
        self.name = name
        self.materials = []
        self.vertices = [object() for _ in range(8)]


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

            def convert(self, target="MESH", keep_original=False, **kwargs):
                bpy.op_calls.append(("object.convert", {"target": target, "keep_original": keep_original, **kwargs}))
                active = bpy.context.view_layer.objects.active or bpy.context.object
                if active is None:
                    return
                if keep_original:
                    converted = FakeObject(f"{active.name}.Mesh", obj_type=target, data=FakeMeshData(f"{active.name}MeshData"))
                    converted.location = list(active.location)
                    converted.rotation_euler = list(active.rotation_euler)
                    converted.scale = list(active.scale)
                    bpy.add(converted)
                    return
                active.type = target
                active.data = FakeMeshData(f"{active.name}MeshData")
                bpy.context.object = active

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
    assert {"geometry.report", "geometry.create_curve", "geometry.set_bezier_spline"} <= names


def test_set_bezier_spline_replaces_points_and_can_close(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("Cheek", data=FakeData("CheekData", splines=[FakeSpline("BEZIER", bezier=2)])))
    reg = build_default_registry()
    out = dispatch_on_main(
        reg,
        "geometry.set_bezier_spline",
        {
            "object": "Cheek",
            "closed": True,
            # Flat [x,y,z, ...] triples -- a real array param, not a JSON-in-a-string.
            "points": [0, -0.4, 0.7, 0, -0.2, 0.8, 0, -0.2, 1.2, 0, 0.3, 1.2],
        },
        ctx,
    )
    spline = bpy.data.objects.get("Cheek").data.splines[0]
    assert spline.use_cyclic_u is True
    assert len(spline.bezier_points) == 4
    assert list(spline.bezier_points[0].co) == [0.0, -0.4, 0.7]
    assert out["splines"][0]["bezier_points"] == 4


def test_set_bezier_spline_rejects_a_partial_triple(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("Cheek", data=FakeData("CheekData", splines=[FakeSpline("BEZIER", bezier=2)])))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "geometry.set_bezier_spline",
            {"object": "Cheek", "points": [0, -0.4, 0.7, 0, -0.2]},
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS
    assert "triples" in exc.value.message


def test_set_bezier_spline_handles_one_type_fills_every_point(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("Cheek", data=FakeData("CheekData", splines=[FakeSpline("BEZIER", bezier=1)])))
    reg = build_default_registry()
    dispatch_on_main(
        reg,
        "geometry.set_bezier_spline",
        {"object": "Cheek", "points": [0, 0, 0, 1, 0, 0, 1, 1, 0], "handles": "VECTOR"},
        ctx,
    )
    points = bpy.data.objects.get("Cheek").data.splines[0].bezier_points
    assert [p.handle_left_type for p in points] == ["VECTOR"] * 3
    assert [p.handle_right_type for p in points] == ["VECTOR"] * 3


def test_set_bezier_spline_handles_can_differ_per_point(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("Cheek", data=FakeData("CheekData", splines=[FakeSpline("BEZIER", bezier=1)])))
    reg = build_default_registry()
    dispatch_on_main(
        reg,
        "geometry.set_bezier_spline",
        {"object": "Cheek", "points": [0, 0, 0, 1, 0, 0, 1, 1, 0], "handles": "VECTOR,AUTO,VECTOR"},
        ctx,
    )
    points = bpy.data.objects.get("Cheek").data.splines[0].bezier_points
    assert [p.handle_left_type for p in points] == ["VECTOR", "AUTO", "VECTOR"]


def test_set_bezier_spline_rejects_a_handle_count_mismatch(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("Cheek", data=FakeData("CheekData", splines=[FakeSpline("BEZIER", bezier=1)])))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "geometry.set_bezier_spline",
            {"object": "Cheek", "points": [0, 0, 0, 1, 0, 0, 1, 1, 0], "handles": "VECTOR,AUTO"},
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS


def test_set_bezier_spline_rejects_an_unknown_handle_type(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("Cheek", data=FakeData("CheekData", splines=[FakeSpline("BEZIER", bezier=1)])))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "geometry.set_bezier_spline",
            {"object": "Cheek", "points": [0, 0, 0], "handles": "SMOOTH"},
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS


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
    assert out["curve"]["use_fill_caps"] is True


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


def test_router_contains_geometry_convert_to_mesh() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert "geometry.convert_to_mesh" in names


def test_convert_to_mesh_uses_object_context_and_renames(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    curve = bpy.add(FakeObject("CurveHero", data=FakeData("CurveData")))
    curve.mode = "EDIT"
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry.convert_to_mesh",
        {"object": "CurveHero", "name": "CurveMesh", "keep_original": False},
        ctx,
    )

    assert out["name"] == "CurveMesh"
    assert out["type"] == "MESH"
    assert bpy.data.objects.get("CurveMesh").data.name == "CurveHeroMeshData"
    assert ("object.convert", {"target": "MESH", "keep_original": False}) in bpy.op_calls
    assert bpy.mode_calls == ["OBJECT", "EDIT"]


def test_convert_to_mesh_can_keep_original(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.add(FakeObject("CurveHero", data=FakeData("CurveData")))
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry.convert_to_mesh",
        {"object": "CurveHero", "name": "CurveMeshCopy", "keep_original": True},
        ctx,
    )

    assert out["name"] == "CurveMeshCopy"
    assert out["type"] == "MESH"
    assert bpy.data.objects.get("CurveHero").type == "CURVE"
    assert bpy.data.objects.get("CurveMeshCopy").type == "MESH"
