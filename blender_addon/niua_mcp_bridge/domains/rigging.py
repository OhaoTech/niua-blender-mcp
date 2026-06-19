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


def list_bones(ctx: Ctx, payload: dict) -> dict:
    armature = _resolve_armature(ctx, payload.get("armature"))
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
    return {"armature": armature.name, "bone_count": len(out), "bones": out}


COMMANDS = [
    Command("rig.add_armature", add_armature, mutates=True, feedback="viewport"),
    Command("rig.add_bone", add_bone, mutates=True, feedback="viewport"),
    Command("rig.set_bone_transform", set_bone_transform, mutates=True, feedback="viewport"),
    Command("rig.parent_with_auto_weights", parent_with_auto_weights, mutates=True, feedback="viewport"),
    Command("rig.list_bones", list_bones, mutates=False),
]
