"""Object domain handlers: lifecycle, transforms, origins, and bounds."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import HANDLER_ERROR, INVALID_PARAMS, PRECONDITION, BridgeError
from .shading import _ensure_nodes, _link_sockets, _principled

_PRIMITIVES = {
    "CUBE": ("mesh", "primitive_cube_add"),
    "SPHERE": ("mesh", "primitive_uv_sphere_add"),
    "PLANE": ("mesh", "primitive_plane_add"),
    "CYLINDER": ("mesh", "primitive_cylinder_add"),
    "CONE": ("mesh", "primitive_cone_add"),
    "TORUS": ("mesh", "primitive_torus_add"),
    "MONKEY": ("mesh", "primitive_monkey_add"),
    "EMPTY": ("object", "empty_add"),
}


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in value]
    except TypeError:
        return []


def _matrix_rows(matrix: Any) -> list[list[float]]:
    if matrix is None:
        return []
    try:
        return [[float(value) for value in row] for row in matrix]
    except TypeError:
        return []


def _collection_names(obj: Any) -> list[str]:
    return [getattr(collection, "name", "") for collection in getattr(obj, "users_collection", []) or []]


def _vec(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise BridgeError(INVALID_PARAMS, "expected a 3-item array")
    return [float(item) for item in value]


def _object_state(obj: Any) -> dict:
    parent = getattr(obj, "parent", None)
    return {
        "name": getattr(obj, "name", ""),
        "type": getattr(obj, "type", ""),
        "location": _float_list(getattr(obj, "location", [])),
        "rotation": _float_list(getattr(obj, "rotation_euler", [])),
        "scale": _float_list(getattr(obj, "scale", [])),
        "delta_location": _float_list(getattr(obj, "delta_location", [])),
        "delta_rotation": _float_list(getattr(obj, "delta_rotation_euler", [])),
        "delta_scale": _float_list(getattr(obj, "delta_scale", [])),
        "rotation_mode": getattr(obj, "rotation_mode", ""),
        "dimensions": _float_list(getattr(obj, "dimensions", [])),
        "parent": getattr(parent, "name", None) if parent is not None else None,
        "collections": _collection_names(obj),
        "matrix_world": _matrix_rows(getattr(obj, "matrix_world", None)),
    }


def _world_point(matrix: Any, corner: Any) -> list[float]:
    if matrix is None:
        return _float_list(corner)
    try:
        from mathutils import Vector  # noqa: PLC0415 - Blender-only import

        return _float_list(matrix @ Vector(corner))
    except Exception:  # noqa: BLE001 - fake bpy and partial objects use simpler matrices
        try:
            return _float_list(matrix @ corner)
        except Exception:  # noqa: BLE001
            return _float_list(corner)


def _center(corners: list[list[float]]) -> list[float]:
    if not corners:
        return []
    return [sum(corner[i] for corner in corners) / len(corners) for i in range(3)]


def _rounded_vec(values: list[float]) -> list[float]:
    return [round(float(value), 10) for value in values]


def _bounds_state(obj: Any) -> dict:
    local = [_float_list(corner) for corner in (getattr(obj, "bound_box", []) or [])]
    matrix = getattr(obj, "matrix_world", None)
    world = [_world_point(matrix, corner) for corner in local]
    return {
        "object": getattr(obj, "name", ""),
        "dimensions": _float_list(getattr(obj, "dimensions", [])),
        "local": local,
        "world": world,
        "center": _center(world),
    }


def _create_box_proxy(ctx: Ctx, name: str, center: list[float], dimensions: list[float], before: set[str]) -> Any:
    ctx.bpy.ops.mesh.primitive_cube_add(size=1.0, location=_rounded_vec(center))
    proxy = _created(ctx, before)
    proxy.name = name
    proxy.dimensions = _rounded_vec(dimensions)
    if hasattr(proxy, "display_type"):
        proxy.display_type = "WIRE"
    before.add(getattr(proxy, "name", ""))
    return proxy


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


def _create_kwargs(otype: str, payload: dict) -> dict:
    location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    rotation = _vec(payload.get("rotation"), [0.0, 0.0, 0.0])
    scale = _vec(payload.get("scale"), [1.0, 1.0, 1.0])
    calc_uvs = bool(payload.get("calc_uvs", True))

    if otype in {"CUBE", "PLANE", "MONKEY"}:
        return {
            "size": float(payload.get("size", 2.0)),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "SPHERE":
        return {
            "segments": int(payload.get("vertices", 32)),
            "radius": float(payload.get("radius", 1.0)),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "CYLINDER":
        return {
            "vertices": int(payload.get("vertices", 32)),
            "radius": float(payload.get("radius", 1.0)),
            "depth": float(payload.get("depth", 2.0)),
            "end_fill_type": str(payload.get("end_fill_type", "NGON")),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "CONE":
        return {
            "vertices": int(payload.get("vertices", 32)),
            "radius1": float(payload.get("radius1", 1.0)),
            "radius2": float(payload.get("radius2", 0.0)),
            "depth": float(payload.get("depth", 2.0)),
            "end_fill_type": str(payload.get("end_fill_type", "NGON")),
            "calc_uvs": calc_uvs,
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    if otype == "TORUS":
        return {
            "major_radius": float(payload.get("major_radius", 1.0)),
            "minor_radius": float(payload.get("minor_radius", 0.25)),
            "major_segments": int(payload.get("major_segments", 48)),
            "minor_segments": int(payload.get("minor_segments", 12)),
            "location": location,
            "rotation": rotation,
        }
    if otype == "EMPTY":
        return {
            "type": str(payload.get("empty_display_type", "PLAIN_AXES")),
            "radius": float(payload.get("radius", 1.0)),
            "location": location,
            "rotation": rotation,
            "scale": scale,
        }
    raise BridgeError(INVALID_PARAMS, f"unsupported object type: {otype}")


def create_object(ctx: Ctx, payload: dict) -> dict:
    otype = str(payload.get("type", "")).upper()
    if otype not in _PRIMITIVES:
        raise BridgeError(INVALID_PARAMS, f"unsupported object type: {otype}")

    before = {getattr(obj, "name", "") for obj in _scene_objects(ctx)}
    group, op_name = _PRIMITIVES[otype]
    getattr(getattr(ctx.bpy.ops, group), op_name)(**_create_kwargs(otype, payload))
    obj = _created(ctx, before)

    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
    if otype == "TORUS":
        obj.scale = _vec(payload.get("scale"), [1.0, 1.0, 1.0])
    return _object_state(obj)


def _parse_objects(ctx: Ctx, raw: Any) -> list[Any]:
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "objects is required")
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise BridgeError(INVALID_PARAMS, "objects must contain at least one object name")
    return [ctx.get_object(name) for name in names]


def _link_duplicate(ctx: Ctx, source: Any, duplicate: Any) -> None:
    collections = list(getattr(source, "users_collection", []) or [])
    if not collections:
        collections = [ctx.bpy.context.scene.collection]
    for collection in collections:
        collection.objects.link(duplicate)

    # Real Blender adds linked object IDs to bpy.data.objects automatically. Fake-bpy
    # list collections need an explicit hook so tests can resolve the duplicate.
    objects = getattr(ctx.bpy.data, "objects", None)
    if hasattr(objects, "add") and objects.get(getattr(duplicate, "name", "")) is None:
        objects.add(duplicate)


def duplicate(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    linked = bool(payload.get("linked", False))
    offset = _vec(payload.get("offset"), [0.0, 0.0, 0.0])
    new_obj = obj.copy()

    name = payload.get("name")
    if isinstance(name, str) and name:
        new_obj.name = name

    if not linked:
        data = getattr(obj, "data", None)
        if data is not None and hasattr(data, "copy"):
            new_obj.data = data.copy()

    base_location = _float_list(getattr(obj, "location", []))
    if len(base_location) == 3:
        new_obj.location = [base_location[i] + offset[i] for i in range(3)]

    _link_duplicate(ctx, obj, new_obj)
    return _object_state(new_obj)


def lod_create(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    level = int(payload.get("level", 1))
    if level < 1:
        raise BridgeError(INVALID_PARAMS, "level must be >= 1")
    ratio = float(payload.get("ratio", 0.5))
    if ratio <= 0.0 or ratio > 1.0:
        raise BridgeError(INVALID_PARAMS, "ratio must be > 0 and <= 1")
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        name = f"{getattr(obj, 'name', 'Object')}_LOD{level}"

    lod = obj.copy()
    lod.name = name
    data = getattr(obj, "data", None)
    if data is not None and hasattr(data, "copy"):
        lod.data = data.copy()
    _link_duplicate(ctx, obj, lod)

    modifier_name = "LOD_DECIMATE"
    modifiers = getattr(lod, "modifiers", None)
    modifier = None
    if modifiers is not None and hasattr(modifiers, "new"):
        modifier = modifiers.new(name=modifier_name, type="DECIMATE")
        modifier.ratio = ratio

    applied = bool(payload.get("apply", False))
    if applied and modifier is not None:
        with ctx.ensure(active=lod, mode="OBJECT", select=[lod]):
            ctx.check_poll(ctx.bpy.ops.object.modifier_apply)
            ctx.bpy.ops.object.modifier_apply(modifier=modifier.name)
    return {
        "object": getattr(obj, "name", ""),
        "lod": getattr(lod, "name", ""),
        "level": level,
        "ratio": ratio,
        "modifier": modifier_name if modifier is not None else None,
        "applied": applied,
    }


def collision_proxy_create(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    shape = str(payload.get("shape", "BOX")).upper()
    if shape != "BOX":
        raise BridgeError(INVALID_PARAMS, f"unsupported collision proxy shape: {shape}")
    margin = float(payload.get("margin", 0.0))
    if margin < 0.0:
        raise BridgeError(INVALID_PARAMS, "margin must be >= 0")
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        name = f"{getattr(obj, 'name', 'Object')}_COL"

    bounds_state = _bounds_state(obj)
    center = bounds_state["center"] or _float_list(getattr(obj, "location", [0.0, 0.0, 0.0]))
    dimensions = bounds_state["dimensions"] or _float_list(getattr(obj, "dimensions", [1.0, 1.0, 1.0]))
    dimensions = [float(dim) + (margin * 2.0) for dim in dimensions]
    before = {getattr(candidate, "name", "") for candidate in _scene_objects(ctx)}
    proxy = _create_box_proxy(ctx, name, center, dimensions, before)
    return {
        "object": getattr(obj, "name", ""),
        "proxy": getattr(proxy, "name", ""),
        "shape": shape,
        "dimensions": _rounded_vec(dimensions),
    }


def collision_hulls_create(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    count = int(payload.get("count", 2))
    if count < 2:
        raise BridgeError(INVALID_PARAMS, "count must be >= 2")
    if count > 16:
        raise BridgeError(INVALID_PARAMS, "count must be <= 16")
    margin = float(payload.get("margin", 0.0))
    if margin < 0.0:
        raise BridgeError(INVALID_PARAMS, "margin must be >= 0")

    bounds_state = _bounds_state(obj)
    center = bounds_state["center"] or _float_list(getattr(obj, "location", [0.0, 0.0, 0.0]))
    dimensions = bounds_state["dimensions"] or _float_list(getattr(obj, "dimensions", [1.0, 1.0, 1.0]))
    axis = str(payload.get("axis", "LONGEST")).upper()
    if axis == "LONGEST":
        axis_index = max(range(3), key=lambda i: dimensions[i])
    elif axis in {"X", "Y", "Z"}:
        axis_index = {"X": 0, "Y": 1, "Z": 2}[axis]
    else:
        raise BridgeError(INVALID_PARAMS, f"unsupported collision hull axis: {axis}")
    axis_name = ["X", "Y", "Z"][axis_index]

    name_prefix = payload.get("name_prefix")
    if not isinstance(name_prefix, str) or not name_prefix:
        name_prefix = f"{getattr(obj, 'name', 'Object')}_COL"

    segment = dimensions[axis_index] / count
    before = {getattr(candidate, "name", "") for candidate in _scene_objects(ctx)}
    names: list[str] = []
    proxy_dimensions: list[list[float]] = []
    for index in range(count):
        proxy_center = list(center)
        proxy_center[axis_index] = center[axis_index] - (dimensions[axis_index] / 2.0) + (segment * (index + 0.5))
        dims = [float(dim) + (margin * 2.0) for dim in dimensions]
        dims[axis_index] = segment + (margin * 2.0)
        proxy = _create_box_proxy(ctx, f"{name_prefix}_{index:02d}", proxy_center, dims, before)
        names.append(getattr(proxy, "name", ""))
        proxy_dimensions.append(_rounded_vec(dims))

    return {
        "object": getattr(obj, "name", ""),
        "axis": axis_name,
        "count": count,
        "proxies": names,
        "dimensions": proxy_dimensions,
    }


def delete(ctx: Ctx, payload: dict) -> dict:
    objects = _parse_objects(ctx, payload.get("objects"))
    names = [getattr(obj, "name", "") for obj in objects]
    for obj in objects:
        ctx.bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": names, "count": len(names)}


def rename(ctx: Ctx, payload: dict) -> dict:
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        raise BridgeError(INVALID_PARAMS, "name is required")
    obj = ctx.get_object(payload.get("object"))
    obj.name = name
    return _object_state(obj)


def transform_set(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    if "rotation_mode" in payload:
        obj.rotation_mode = str(payload.get("rotation_mode"))
    if "location" in payload:
        obj.location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    if "rotation" in payload:
        obj.rotation_euler = _vec(payload.get("rotation"), [0.0, 0.0, 0.0])
    if "scale" in payload:
        obj.scale = _vec(payload.get("scale"), [1.0, 1.0, 1.0])
    if "delta_location" in payload:
        obj.delta_location = _vec(payload.get("delta_location"), [0.0, 0.0, 0.0])
    if "delta_rotation" in payload:
        obj.delta_rotation_euler = _vec(payload.get("delta_rotation"), [0.0, 0.0, 0.0])
    if "delta_scale" in payload:
        obj.delta_scale = _vec(payload.get("delta_scale"), [1.0, 1.0, 1.0])
    return _object_state(obj)


def transform_apply(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    applied = {
        "location": bool(payload.get("location", True)),
        "rotation": bool(payload.get("rotation", True)),
        "scale": bool(payload.get("scale", True)),
        "properties": bool(payload.get("properties", True)),
        "isolate_users": bool(payload.get("isolate_users", False)),
    }
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(ctx.bpy.ops.object.transform_apply)
        ctx.bpy.ops.object.transform_apply(**applied)
    return {"object": getattr(obj, "name", ""), "applied": applied}


def origin_set(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    otype = str(payload.get("type", "ORIGIN_GEOMETRY"))
    center = str(payload.get("center", "MEDIAN"))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(ctx.bpy.ops.object.origin_set)
        ctx.bpy.ops.object.origin_set(type=otype, center=center)
    return {"object": getattr(obj, "name", ""), "origin": otype, "center": center}


def transform_get(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    return _object_state(obj)


def bounds(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    return _bounds_state(obj)


def _bake_target_material(ctx: Ctx, tgt: Any) -> Any:
    """Resolve (or create) the material that receives the baked maps, and make sure
    it is attached to the target's material slots and uses nodes."""
    mat = getattr(tgt, "active_material", None)
    if mat is None:
        mat = ctx.bpy.data.materials.new(name=f"{getattr(tgt, 'name', 'Object')}_baked")
        data = getattr(tgt, "data", None)
        materials = getattr(data, "materials", None)
        if materials is None:
            raise BridgeError(PRECONDITION, f"object cannot hold materials: {getattr(tgt, 'name', '')}")
        materials.append(mat)
        if hasattr(tgt, "active_material_index"):
            tgt.active_material_index = len(list(materials)) - 1
    return mat


def bake_transfer(ctx: Ctx, payload: dict) -> dict:
    """Bake high->low detail (selected-to-active) from ``source`` into new image
    textures on ``target``'s material, and wire the NORMAL map into the target's
    Principled BSDF normal input. Requires ``target`` to already have UVs.
    """
    src = ctx.get_object(payload.get("source"))
    tgt = ctx.get_object(payload.get("target"))
    if getattr(src, "type", "") != "MESH" or getattr(tgt, "type", "") != "MESH":
        raise BridgeError(INVALID_PARAMS, "source and target must be mesh objects")
    if not getattr(getattr(tgt, "data", None), "uv_layers", None):
        raise BridgeError(PRECONDITION, "target has no UVs; unwrap before baking")

    maps = [m.strip().upper() for m in str(payload.get("maps", "NORMAL,AO")).split(",") if m.strip()]
    if not maps:
        raise BridgeError(INVALID_PARAMS, "maps must contain at least one map name")
    size = int(payload.get("size", 1024))
    if size < 1:
        raise BridgeError(INVALID_PARAMS, "size must be >= 1")
    ray_distance = float(payload.get("ray_distance", 0.01))
    if ray_distance < 0.0:
        raise BridgeError(INVALID_PARAMS, "ray_distance must be >= 0")

    mat = _bake_target_material(ctx, tgt)
    node_tree = _ensure_nodes(mat)
    principled = _principled(node_tree)

    scene = ctx.bpy.context.scene
    prev_engine = scene.render.engine
    scene.render.engine = "CYCLES"  # object.bake requires Cycles

    baked: list[str] = []
    images: list[str] = []
    try:
        with ctx.ensure(active=tgt, mode="OBJECT", select=[src, tgt]):
            ctx.check_poll(ctx.bpy.ops.object.bake)
            for map_name in maps:
                image = ctx.bpy.data.images.new(
                    name=f"{getattr(tgt, 'name', 'Object')}_{map_name}",
                    width=size,
                    height=size,
                    alpha=False,
                    float_buffer=(map_name == "NORMAL"),
                )
                colorspace = getattr(image, "colorspace_settings", None)
                if map_name == "NORMAL" and colorspace is not None and hasattr(colorspace, "name"):
                    colorspace.name = "Non-Color"
                node = node_tree.nodes.new("ShaderNodeTexImage")
                node.name = getattr(image, "name", map_name)
                node.label = map_name
                node.image = image
                node_tree.nodes.active = node

                scene.cycles.bake_type = map_name
                ctx.bpy.ops.object.bake(
                    type=map_name,
                    use_selected_to_active=True,
                    cage_extrusion=ray_distance,
                    use_clear=True,
                )

                if map_name == "NORMAL" and principled is not None:
                    normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
                    normal_map.name = f"{getattr(image, 'name', 'Normal')}_NORMAL_MAP"
                    normal_map.label = "NORMAL_MAP"
                    _link_sockets(node_tree, node.outputs["Color"], normal_map.inputs["Color"])
                    _link_sockets(node_tree, normal_map.outputs["Normal"], principled.inputs["Normal"])

                baked.append(map_name)
                images.append(getattr(image, "name", ""))
    finally:
        scene.render.engine = prev_engine

    return {"object": getattr(tgt, "name", ""), "baked": baked, "images": images}


COMMANDS = [
    Command("object.create", create_object, mutates=True, feedback="viewport"),
    Command("object.duplicate", duplicate, mutates=True, feedback="viewport"),
    Command("object.lod_create", lod_create, mutates=True, feedback="viewport"),
    Command("object.collision_proxy_create", collision_proxy_create, mutates=True, feedback="viewport"),
    Command("object.collision_hulls_create", collision_hulls_create, mutates=True, feedback="viewport"),
    Command("object.delete", delete, mutates=True, feedback="viewport"),
    Command("object.rename", rename, mutates=True, feedback="viewport"),
    Command("object.transform_set", transform_set, mutates=True, feedback="viewport"),
    Command("object.transform_apply", transform_apply, mutates=True, feedback="viewport"),
    Command("object.origin_set", origin_set, mutates=True, feedback="viewport"),
    Command("object.transform_get", transform_get, mutates=False),
    Command("object.bounds", bounds, mutates=False),
    Command("object.bake_transfer", bake_transfer, mutates=True, feedback="viewport", timeout_tier="heavy"),
]
