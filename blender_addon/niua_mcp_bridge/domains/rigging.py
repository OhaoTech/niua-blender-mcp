"""Rigging domain handlers: armatures, bones, and auto-weight skinning.

Handlers stay tiny: the kernel does validation, undo and (for edit ops) context. Bones
are authored as *edit bones*, which only exist while the armature object is in EDIT mode,
so ``rig.add_bone`` / ``rig.set_bone_transform`` run inside ``ctx.ensure(mode="EDIT")`` on
the armature. ``rig.parent_with_auto_weights`` is an object-mode op: it selects the mesh,
makes the armature active, and runs ``object.parent_set`` type=ARMATURE_AUTO.
``rig.list_bones`` is read-only and reads the (always-available) object-mode bone list.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import NOT_FOUND, PRECONDITION, BridgeError


def _resolve_armature(ctx: Ctx, name: Any) -> Any:
    """Return a named armature object, failing cleanly if missing or wrong type."""
    if not isinstance(name, str) or not name:
        raise BridgeError(PRECONDITION, "armature is required")
    obj = ctx.get_object(name)  # raises NOT_FOUND if absent
    if getattr(obj, "type", None) != "ARMATURE":
        raise BridgeError(
            PRECONDITION,
            f"object is not an armature: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    return obj


def _resolve_mesh(ctx: Ctx, name: Any) -> Any:
    """Return a named mesh object, failing cleanly if missing or wrong type."""
    if not isinstance(name, str) or not name:
        raise BridgeError(PRECONDITION, "mesh is required")
    obj = ctx.get_object(name)
    if getattr(obj, "type", None) != "MESH":
        raise BridgeError(
            PRECONDITION,
            f"object is not a mesh: {getattr(obj, 'name', '?')}",
            {"type": getattr(obj, "type", None)},
        )
    return obj


def _vec(value: Any, default: list[float]) -> list[float]:
    if value is None:
        return list(default)
    return [float(v) for v in value]


def _created(bpy: Any, before: set[str]) -> Any:
    """Return the object created by the last add op (active, else newest in scene)."""
    obj = getattr(bpy.context, "object", None)
    if obj is not None and getattr(obj, "name", "") not in before:
        return obj
    for candidate in reversed(list(bpy.context.scene.objects)):
        if getattr(candidate, "name", "") not in before:
            return candidate
    raise BridgeError(PRECONDITION, "no armature was created")


def add_armature(ctx: Ctx, payload: dict) -> dict:
    bpy = ctx.bpy
    location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
    before = {getattr(o, "name", "") for o in bpy.context.scene.objects}
    bpy.ops.object.armature_add(location=location)
    obj = _created(bpy, before)
    name = payload.get("name")
    if isinstance(name, str) and name:
        obj.name = name
    return {"armature": obj.name, "location": location}


def add_bone(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
    bone_name = payload.get("name")
    if not isinstance(bone_name, str) or not bone_name:
        raise BridgeError(PRECONDITION, "bone name is required")
    head = _vec(payload.get("head"), [0.0, 0.0, 0.0])
    tail = _vec(payload.get("tail"), [0.0, 0.0, 1.0])

    with ctx.ensure(active=armature, mode="EDIT", select=[armature]):
        edit_bones = armature.data.edit_bones
        bone = edit_bones.new(bone_name)
        bone.head = head
        bone.tail = tail
        # new() may uniquify the name (e.g. on collision); report the real one.
        bone_name = getattr(bone, "name", bone_name)
    return {"armature": armature.name, "bone": bone_name, "head": head, "tail": tail}


def set_bone_transform(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
    bone_name = payload.get("bone")
    if not isinstance(bone_name, str) or not bone_name:
        raise BridgeError(PRECONDITION, "bone is required")
    head = payload.get("head")
    tail = payload.get("tail")

    applied: dict[str, list[float]] = {}
    with ctx.ensure(active=armature, mode="EDIT", select=[armature]):
        bone = armature.data.edit_bones.get(bone_name)
        if bone is None:
            raise BridgeError(NOT_FOUND, f"bone not found: {bone_name}")
        if head is not None:
            bone.head = _vec(head, [0.0, 0.0, 0.0])
            applied["head"] = list(bone.head)
        if tail is not None:
            bone.tail = _vec(tail, [0.0, 0.0, 1.0])
            applied["tail"] = list(bone.tail)
    return {"armature": armature.name, "bone": bone_name, **applied}


def parent_with_auto_weights(ctx: Ctx, payload: dict) -> dict:
    mesh = _resolve_mesh(ctx, payload.get("mesh"))
    armature = _resolve_armature(ctx, payload.get("armature"))
    # Object-mode bind: mesh selected, armature active, parent_set ARMATURE_AUTO.
    with ctx.ensure(active=armature, mode="OBJECT", select=[mesh, armature]):
        ctx.check_poll(ctx.bpy.ops.object.parent_set)
        ctx.bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    return {"mesh": mesh.name, "armature": armature.name, "parented": True}


def _bone_entries(armature: Any) -> list[dict]:
    bones = list(getattr(armature.data, "bones", []) or [])
    out = []
    for bone in bones:
        head = getattr(bone, "head_local", None)
        if head is None:
            head = getattr(bone, "head", None)
        tail = getattr(bone, "tail_local", None)
        if tail is None:
            tail = getattr(bone, "tail", None)
        out.append(
            {
                "name": getattr(bone, "name", "?"),
                "head": [float(v) for v in head] if head is not None else None,
                "tail": [float(v) for v in tail] if tail is not None else None,
                "parent": getattr(getattr(bone, "parent", None), "name", None),
            }
        )
    return out


def list_bones(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
    out = _bone_entries(armature)
    return {"armature": armature.name, "bone_count": len(out), "bones": out}


def _constraint_entries(pose_bone: Any) -> list[dict]:
    out = []
    for constraint in list(getattr(pose_bone, "constraints", []) or []):
        target = getattr(constraint, "target", None)
        out.append(
            {
                "name": getattr(constraint, "name", "?"),
                "type": getattr(constraint, "type", None),
                "influence": float(getattr(constraint, "influence", 0.0) or 0.0),
                "target": getattr(target, "name", None) if target is not None else None,
                "subtarget": getattr(constraint, "subtarget", ""),
                "mute": bool(getattr(constraint, "mute", False)),
            }
        )
    return out


def _pose_bones(armature: Any) -> list[Any]:
    pose = getattr(armature, "pose", None)
    return list(getattr(pose, "bones", []) or [])


def _get_pose_bone(armature: Any, name: Any) -> Any:
    if not isinstance(name, str) or not name:
        raise BridgeError(PRECONDITION, "bone is required")
    bones = getattr(getattr(armature, "pose", None), "bones", None)
    getter = getattr(bones, "get", None)
    pose_bone = getter(name) if callable(getter) else None
    if pose_bone is None:
        pose_bone = next((candidate for candidate in list(bones or []) if getattr(candidate, "name", None) == name), None)
    if pose_bone is None:
        raise BridgeError(NOT_FOUND, f"pose bone not found: {name}", {"armature": getattr(armature, "name", "?")})
    return pose_bone


def _pose_bone_entry(pose_bone: Any) -> dict:
    return {
        "name": getattr(pose_bone, "name", "?"),
        "location": [float(v) for v in getattr(pose_bone, "location", [0.0, 0.0, 0.0])],
        "rotation_mode": getattr(pose_bone, "rotation_mode", None),
        "rotation_euler": [float(v) for v in getattr(pose_bone, "rotation_euler", [0.0, 0.0, 0.0])],
        "scale": [float(v) for v in getattr(pose_bone, "scale", [1.0, 1.0, 1.0])],
        "constraints": _constraint_entries(pose_bone),
    }


def _pose_report(armature: Any, bone_name: Any = None) -> dict:
    if isinstance(bone_name, str) and bone_name:
        entries = [_pose_bone_entry(_get_pose_bone(armature, bone_name))]
    else:
        entries = [_pose_bone_entry(pose_bone) for pose_bone in _pose_bones(armature)]
    return {"armature": armature.name, "pose_bone_count": len(entries), "pose_bones": entries}


def pose_report(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
    return _pose_report(armature, payload.get("bone"))


def set_pose_bone(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
    pose_bone = _get_pose_bone(armature, payload.get("bone"))
    with ctx.ensure(active=armature, mode="POSE", select=[armature]):
        if payload.get("location") is not None:
            pose_bone.location = _vec(payload.get("location"), [0.0, 0.0, 0.0])
        if payload.get("rotation_mode") is not None:
            pose_bone.rotation_mode = str(payload["rotation_mode"])
        if payload.get("rotation") is not None:
            if payload.get("rotation_mode") is None:
                pose_bone.rotation_mode = "XYZ"
            pose_bone.rotation_euler = _vec(payload.get("rotation"), [0.0, 0.0, 0.0])
        if payload.get("scale") is not None:
            pose_bone.scale = _vec(payload.get("scale"), [1.0, 1.0, 1.0])
    return {"armature": armature.name, "pose_bone": _pose_bone_entry(pose_bone)}


def _clear_pose_bone(pose_bone: Any) -> None:
    pose_bone.location = [0.0, 0.0, 0.0]
    if hasattr(pose_bone, "rotation_euler"):
        pose_bone.rotation_euler = [0.0, 0.0, 0.0]
    if hasattr(pose_bone, "rotation_quaternion"):
        try:
            pose_bone.rotation_quaternion = [1.0, 0.0, 0.0, 0.0]
        except Exception:  # noqa: BLE001 - some fakes/properties may reject this shape
            pass
    pose_bone.scale = [1.0, 1.0, 1.0]


def clear_pose(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
    with ctx.ensure(active=armature, mode="POSE", select=[armature]):
        for pose_bone in _pose_bones(armature):
            _clear_pose_bone(pose_bone)
    return _pose_report(armature)


def report(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
    bones = _bone_entries(armature)
    pose = _pose_report(armature)
    child_meshes = [
        getattr(obj, "name", "?")
        for obj in list(getattr(ctx.bpy.context.scene, "objects", []) or [])
        if getattr(obj, "parent", None) is armature and getattr(obj, "type", None) == "MESH"
    ]
    return {
        "armature": armature.name,
        "bone_count": len(bones),
        "bones": bones,
        "pose_bone_count": pose["pose_bone_count"],
        "pose_bones": pose["pose_bones"],
        "child_meshes": child_meshes,
    }


COMMANDS = [
    Command("rig.add_armature", add_armature, mutates=True, feedback="viewport"),
    Command("rig.add_bone", add_bone, mutates=True, feedback="viewport"),
    Command("rig.set_bone_transform", set_bone_transform, mutates=True, feedback="viewport"),
    Command("rig.parent_with_auto_weights", parent_with_auto_weights, mutates=True, feedback="viewport"),
    Command("rig.list_bones", list_bones, mutates=False),
    Command("rig.report", report, mutates=False),
    Command("rig.pose_report", pose_report, mutates=False),
    Command("rig.set_pose_bone", set_pose_bone, mutates=True, feedback="viewport"),
    Command("rig.clear_pose", clear_pose, mutates=True, feedback="viewport"),
]
