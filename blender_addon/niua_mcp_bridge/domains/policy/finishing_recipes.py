"""Finishing recipes: multi-step opinionated pipelines, not Blender translation.

Every tool here is a *recipe* -- several stock Blender operations sequenced according to
an opinion about what a game asset should be. That is a different kind of thing from the
rest of ``domains/``, which translates one Blender capability into one tool and lets the
agent decide the sequence.

They live in ``policy/`` because the opinions are not good enough to ship. ``retopo`` in
particular reaches its triangle budget on simple props but cannot take a dense character
there without destroying it, and a tool that fails on the hard case is worse than no tool
at all: it looks like the MCP is broken when the underlying Blender surface is fine.

Nothing is lost by their absence. ``modifiers.add`` with a ``DECIMATE`` modifier,
``mesh.*``, ``uv.*`` and ``object.shrinkwrap`` are all still there, unopinionated, and an
agent can sequence them however the asset actually needs -- which is the whole premise.

Shared plumbing (``_rounded_vec``, ``_created``, ``_bounds_state``, ``_scene_objects``)
is imported from the neutral ``..objects`` module: policy may depend on interface, never
the reverse.
"""

from __future__ import annotations

from typing import Any

from ...context import Ctx
from ...dispatch import Command
from ...errors import INVALID_PARAMS, BridgeError
from ..objects import _bounds_state, _created, _float_list, _link_duplicate, _rounded_vec, _scene_objects

def _create_box_proxy(ctx: Ctx, name: str, center: list[float], dimensions: list[float], before: set[str]) -> Any:
    ctx.bpy.ops.mesh.primitive_cube_add(size=1.0, location=_rounded_vec(center))
    proxy = _created(ctx, before)
    proxy.name = name
    proxy.dimensions = _rounded_vec(dimensions)
    if hasattr(proxy, "display_type"):
        proxy.display_type = "WIRE"
    before.add(getattr(proxy, "name", ""))
    return proxy
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
_VOXEL_COUNT_CAP = 5_000_000
def _capped_voxel_size(dims: list[float], voxel_size: float) -> float:
    """Raise voxel_size (never lower it) so the approximate voxel count implied by the
    object's bbox stays under _VOXEL_COUNT_CAP. Prevents object.voxel_remesh from OOM-ing
    / crashing Blender on large and/or dense (e.g. multi-part) meshes -- this is what
    segfaulted Blender on the 10-part real_multipart mesh before the cap existed.
    """
    if len(dims) < 3 or voxel_size <= 0.0:
        return voxel_size
    bbox_volume = dims[0] * dims[1] * dims[2]
    if bbox_volume <= 0.0:
        return voxel_size
    voxel_count = bbox_volume / (voxel_size**3)
    if voxel_count <= _VOXEL_COUNT_CAP:
        return voxel_size
    capped = (bbox_volume / _VOXEL_COUNT_CAP) ** (1.0 / 3.0)
    return max(voxel_size, capped)
# Voxel remesh has segfaulted Blender on multi-island / high non-manifold generator
# meshes (C-level; Python cannot catch). Prefer decimate-only when risk is high.
_VOXEL_UNSAFE_PARTS = 2
_VOXEL_UNSAFE_NON_MANIFOLD = 5000
def _mesh_topology_risk(mesh: Any) -> dict[str, int]:
    """Return loose-part count and non-manifold edge count (0s if bmesh unavailable)."""
    try:
        import bmesh  # type: ignore
    except ImportError:
        return {"parts": 0, "non_manifold_edges": 0}
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
        seen: set[int] = set()
        parts = 0
        for v in bm.verts:
            if v.index in seen:
                continue
            parts += 1
            stack = [v]
            seen.add(v.index)
            while stack:
                cur = stack.pop()
                for e in cur.link_edges:
                    other = e.other_vert(cur)
                    if other.index not in seen:
                        seen.add(other.index)
                        stack.append(other)
        return {"parts": parts, "non_manifold_edges": non_manifold}
    finally:
        bm.free()
def _voxel_unsafe(mesh: Any) -> tuple[bool, str]:
    """True when voxel_remesh is likely to crash or destroy multi-part topology."""
    risk = _mesh_topology_risk(mesh)
    if risk["parts"] >= _VOXEL_UNSAFE_PARTS:
        return True, f"loose_parts={risk['parts']}"
    if risk["non_manifold_edges"] >= _VOXEL_UNSAFE_NON_MANIFOLD:
        return True, f"non_manifold_edges={risk['non_manifold_edges']}"
    return False, ""
def _decimate_to_tri_budget(ctx: Ctx, obj: Any, tri_budget: int) -> int:
    """Collapse faces with DECIMATE until tris <= tri_budget. Returns post tris."""
    m = obj.data
    tris = sum((len(p.vertices) - 2) for p in m.polygons)
    if tris <= tri_budget or tri_budget < 1:
        return tris
    ratio = max(1e-6, min(1.0, tri_budget / tris))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        modifier = obj.modifiers.new(name="RETOPO_DECIMATE", type="DECIMATE")
        modifier.ratio = ratio
        ctx.check_poll(ctx.bpy.ops.object.modifier_apply)
        ctx.bpy.ops.object.modifier_apply(modifier=modifier.name)
    m = obj.data
    return sum((len(p.vertices) - 2) for p in m.polygons)
def retopo(ctx: Ctx, payload: dict) -> dict:
    """Retopologize an object to a clean mesh at a face budget.

    Default path: voxel remesh (watertight cleanup) then decimate collapse to guarantee
    the face/tri budget. When the mesh looks crash-prone for voxel remesh (multi-island
    or very high non-manifold counts — the multiparts that have segfaulted Blender), or
    when ``mode='decimate'``, skip voxel and decimate-only. That still hits budget so
    bake_and_finish can continue; shrinkwrap + bake recover surface detail.

    Voxel size is capped so huge bboxes cannot allocate runaway voxels.
    """
    bpy = ctx.bpy
    obj = ctx.get_object(payload.get("object"))
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(INVALID_PARAMS, "retopo target must be a mesh")
    target_faces = int(payload.get("target_faces", 0))
    if target_faces < 1:
        raise BridgeError(INVALID_PARAMS, "target_faces must be >= 1")
    mode = str(payload.get("mode") or "auto").strip().lower()
    tri_budget = target_faces * 2
    path = "voxel+decimate"
    skip_reason = ""

    mesh = obj.data
    if mode == "decimate":
        path = "decimate_only"
        skip_reason = "mode=decimate"
    elif mode == "auto":
        unsafe, skip_reason = _voxel_unsafe(mesh)
        if unsafe:
            path = "decimate_only"

    if path == "voxel+decimate":
        voxel_size = float(payload.get("voxel_size", 0.0))
        adaptivity = float(payload.get("adaptivity", 0.0))
        dims = list(getattr(obj, "dimensions", (0.0, 0.0, 0.0)))
        if voxel_size <= 0.0:
            longest = max(dims) if dims and max(dims) > 0 else 1.0
            voxel_size = longest / 128.0
        voxel_size = _capped_voxel_size(dims, voxel_size)
        try:
            with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
                mesh = obj.data
                mesh.remesh_voxel_size = voxel_size
                if hasattr(mesh, "remesh_voxel_adaptivity"):
                    mesh.remesh_voxel_adaptivity = adaptivity
                ctx.check_poll(bpy.ops.object.voxel_remesh)
                bpy.ops.object.voxel_remesh()
        except RuntimeError as exc:
            # Clean failure from Blender ops — fall back to decimate rather than abort.
            path = "decimate_only"
            skip_reason = f"voxel_runtime:{exc}"

    tris = _decimate_to_tri_budget(ctx, obj, tri_budget)
    faces = len(obj.data.polygons)
    out: dict[str, Any] = {"object": obj.name, "faces": faces, "tris": tris, "path": path}
    if skip_reason:
        out["voxel_skipped"] = skip_reason
    return out


COMMANDS = [
    Command("object.lod_create", lod_create, mutates=True, feedback="viewport"),
    Command("object.collision_proxy_create", collision_proxy_create, mutates=True, feedback="viewport"),
    Command("object.collision_hulls_create", collision_hulls_create, mutates=True, feedback="viewport"),
    Command("object.retopo", retopo, mutates=True, feedback="viewport", timeout_tier="heavy"),
]
