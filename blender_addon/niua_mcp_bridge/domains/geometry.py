"""Non-mesh geometry handlers: curves, text, surfaces, metaballs, grease pencil."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, BridgeError

_CURVE_OPS = {
    "BEZIER": "primitive_bezier_curve_add",
    "BEZIER_CIRCLE": "primitive_bezier_circle_add",
    "NURBS_CURVE": "primitive_nurbs_curve_add",
    "NURBS_CIRCLE": "primitive_nurbs_circle_add",
    "NURBS_PATH": "primitive_nurbs_path_add",
}

_SURFACE_OPS = {
    "CURVE": "primitive_nurbs_surface_curve_add",
    "CIRCLE": "primitive_nurbs_surface_circle_add",
    "SURFACE": "primitive_nurbs_surface_surface_add",
    "CYLINDER": "primitive_nurbs_surface_cylinder_add",
    "SPHERE": "primitive_nurbs_surface_sphere_add",
    "TORUS": "primitive_nurbs_surface_torus_add",
}


def _vec(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise BridgeError(INVALID_PARAMS, "expected a 3-item array")
    return [float(item) for item in value]


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in value]
    except TypeError:
        return []


def _scene_objects(ctx: Ctx) -> list[Any]:
    return list(getattr(ctx.bpy.context.scene, "objects", []) or [])


def _created(ctx: Ctx, before: set[str]) -> Any:
    obj = getattr(ctx.bpy.context, "object", None)
    if obj is not None and getattr(obj, "name", "") not in before:
        return obj
    for candidate in reversed(_scene_objects(ctx)):
        if getattr(candidate, "name", "") not in before:
            return candidate
    raise BridgeError(HANDLER_ERROR, "no object was created")


def _primitive_kwargs(payload: dict) -> dict:
    return {
        "radius": float(payload.get("radius", 1.0)),
        "location": _vec(payload.get("location"), [0.0, 0.0, 0.0]),
        "rotation": _vec(payload.get("rotation"), [0.0, 0.0, 0.0]),
        "scale": _vec(payload.get("scale"), [1.0, 1.0, 1.0]),
    }


def _transform_kwargs(payload: dict) -> dict:
    return {
        "location": _vec(payload.get("location"), [0.0, 0.0, 0.0]),
        "rotation": _vec(payload.get("rotation"), [0.0, 0.0, 0.0]),
        "scale": _vec(payload.get("scale"), [1.0, 1.0, 1.0]),
    }


def _rename(obj: Any, payload: dict) -> None:
    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name


def _text_set(data: Any, payload: dict) -> None:
    for key in ("body", "align_x", "align_y", "size"):
        if key in payload:
            setattr(data, key, payload[key])


def _splines_report(data: Any) -> list[dict]:
    out = []
    for spline in list(getattr(data, "splines", []) or []):
        out.append(
            {
                "type": getattr(spline, "type", ""),
                "bezier_points": len(getattr(spline, "bezier_points", []) or []),
                "points": len(getattr(spline, "points", []) or []),
            }
        )
    return out


def _curve_data_report(data: Any) -> dict:
    keys = [
        "bevel_depth",
        "bevel_resolution",
        "extrude",
        "resolution_u",
        "render_resolution_u",
        "dimensions",
        "fill_mode",
        "use_fill_caps",
    ]
    out: dict[str, Any] = {}
    for key in keys:
        if hasattr(data, key):
            value = getattr(data, key)
            if isinstance(value, (int, float)):
                value = float(value) if isinstance(value, float) else int(value)
            out[key] = value
    return out


def _text_report(data: Any) -> dict:
    keys = ["body", "align_x", "align_y", "size", "space_line", "offset_x", "offset_y"]
    return {key: getattr(data, key) for key in keys if hasattr(data, key)}


def _object_report(obj: Any) -> dict:
    data = getattr(obj, "data", None)
    report = {
        "name": getattr(obj, "name", ""),
        "type": getattr(obj, "type", ""),
        "data_type": type(data).__name__ if data is not None else None,
        "location": _float_list(getattr(obj, "location", [])),
        "rotation": _float_list(getattr(obj, "rotation_euler", [])),
        "scale": _float_list(getattr(obj, "scale", [])),
        "materials": len(getattr(data, "materials", []) or []) if data is not None else 0,
    }
    if data is not None:
        curve = _curve_data_report(data)
        if curve:
            report["curve"] = curve
        text = _text_report(data)
        if text:
            report["text"] = text
        splines = _splines_report(data)
        if splines or hasattr(data, "splines"):
            report["splines"] = splines
        elements = list(getattr(data, "elements", []) or [])
        if elements or hasattr(data, "elements"):
            report["metaball"] = {
                "elements": len(elements),
                "types": [getattr(element, "type", "") for element in elements],
            }
        layers = list(getattr(data, "layers", []) or [])
        if layers or hasattr(data, "layers"):
            report["grease_pencil"] = {
                "layers": len(layers),
                "names": [getattr(layer, "name", "") for layer in layers],
            }
    return report


def report(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    return _object_report(obj)


def create_curve(ctx: Ctx, payload: dict) -> dict:
    curve_type = str(payload.get("type", "")).upper()
    op_name = _CURVE_OPS.get(curve_type)
    if op_name is None:
        raise BridgeError(INVALID_PARAMS, f"unsupported curve type: {curve_type}")
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    getattr(ctx.bpy.ops.curve, op_name)(**_primitive_kwargs(payload))
    obj = _created(ctx, before)
    _rename(obj, payload)
    return _object_report(obj)


def create_text(ctx: Ctx, payload: dict) -> dict:
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    ctx.bpy.ops.object.text_add(**_transform_kwargs(payload))
    obj = _created(ctx, before)
    _rename(obj, payload)
    _text_set(obj.data, payload)
    return _object_report(obj)


def create_surface(ctx: Ctx, payload: dict) -> dict:
    surface_type = str(payload.get("type", "")).upper()
    op_name = _SURFACE_OPS.get(surface_type)
    if op_name is None:
        raise BridgeError(INVALID_PARAMS, f"unsupported surface type: {surface_type}")
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    getattr(ctx.bpy.ops.surface, op_name)(**_primitive_kwargs(payload))
    obj = _created(ctx, before)
    _rename(obj, payload)
    return _object_report(obj)


def create_metaball(ctx: Ctx, payload: dict) -> dict:
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    kwargs = _primitive_kwargs(payload)
    kwargs["type"] = str(payload.get("type", "BALL"))
    ctx.bpy.ops.object.metaball_add(**kwargs)
    obj = _created(ctx, before)
    _rename(obj, payload)
    return _object_report(obj)


def create_grease_pencil(ctx: Ctx, payload: dict) -> dict:
    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    kwargs = _primitive_kwargs(payload)
    kwargs["type"] = str(payload.get("type", "EMPTY"))
    kwargs["use_in_front"] = bool(payload.get("use_in_front", False))
    ctx.bpy.ops.object.grease_pencil_add(**kwargs)
    obj = _created(ctx, before)
    _rename(obj, payload)
    return _object_report(obj)


COMMANDS = [
    Command("geometry.create_curve", create_curve, mutates=True, feedback="viewport"),
    Command("geometry.create_text", create_text, mutates=True, feedback="viewport"),
    Command("geometry.create_surface", create_surface, mutates=True, feedback="viewport"),
    Command("geometry.create_metaball", create_metaball, mutates=True, feedback="viewport"),
    Command("geometry.create_grease_pencil", create_grease_pencil, mutates=True, feedback="viewport"),
    Command("geometry.report", report, mutates=False),
]
