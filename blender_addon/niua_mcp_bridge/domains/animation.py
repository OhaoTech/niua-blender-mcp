"""Animation domain handlers: set_frame, insert/delete keyframe, interpolation, reports.

Handlers stay tiny: the kernel does validation, undo and (for context-sensitive ops)
context. Keyframing is done through the object datablock's ``keyframe_insert`` /
``keyframe_delete`` methods (no operator poll needed), wrapped in
``ctx.ensure(active=obj, mode="OBJECT", select=[obj])`` so the active object / mode are
guaranteed and restored. ``anim.set_interpolation`` rewrites every keyframe point on the
object's f-curves. ``anim.list_actions`` and ``anim.report`` are read-only feedback.
"""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import PRECONDITION, BridgeError


def _resolve_object(ctx: Ctx, payload: dict) -> Any:
    """Return the target object (named, else active); fail cleanly otherwise."""
    name = payload.get("object")
    if isinstance(name, str) and name:
        return ctx.get_object(name)
    view_layer = getattr(ctx.bpy.context, "view_layer", None)
    obj = getattr(getattr(view_layer, "objects", None), "active", None)
    if obj is None:
        obj = getattr(ctx.bpy.context, "object", None)
    if obj is None:
        raise BridgeError(PRECONDITION, "no active object; pass 'object'")
    return obj


def _current_frame(ctx: Ctx) -> int:
    scene = getattr(ctx.bpy.context, "scene", None)
    return int(getattr(scene, "frame_current", 0) or 0)


def set_frame(ctx: Ctx, payload: dict) -> dict:
    frame = int(payload.get("frame", 0))
    scene = getattr(ctx.bpy.context, "scene", None)
    if scene is None:
        raise BridgeError(PRECONDITION, "no active scene")
    scene.frame_set(frame)
    return {"frame": frame}


def insert_keyframe(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    data_path = str(payload.get("data_path", ""))
    if not data_path:
        raise BridgeError(PRECONDITION, "data_path is required")
    frame = int(payload["frame"]) if payload.get("frame") is not None else _current_frame(ctx)
    index = int(payload.get("index", -1))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ok = obj.keyframe_insert(data_path=data_path, frame=frame, index=index)
    if ok is False:
        raise BridgeError(
            PRECONDITION,
            f"could not insert keyframe on '{data_path}'",
            {"object": obj.name, "data_path": data_path},
        )
    return {"object": obj.name, "data_path": data_path, "frame": frame, "index": index}


def delete_keyframe(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    data_path = str(payload.get("data_path", ""))
    if not data_path:
        raise BridgeError(PRECONDITION, "data_path is required")
    frame = int(payload["frame"]) if payload.get("frame") is not None else _current_frame(ctx)
    index = int(payload.get("index", -1))
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ok = obj.keyframe_delete(data_path=data_path, frame=frame, index=index)
    if ok is False:
        raise BridgeError(
            PRECONDITION,
            f"no keyframe to delete on '{data_path}' at frame {frame}",
            {"object": obj.name, "data_path": data_path, "frame": frame},
        )
    return {"object": obj.name, "data_path": data_path, "frame": frame, "index": index}


def _fcurves(obj: Any) -> list[Any]:
    """Return the object's animation f-curves across Blender action layouts.

    Blender 4.4+ moved f-curves out of ``action.fcurves`` (removed entirely in 5.x)
    into slotted/layered actions: ``action.layers[].strips[].channelbag(slot).fcurves``.
    We try the legacy flat list first (older Blender / fake-bpy unit tests), then fall
    back to walking layered channelbags for the object's active action slot.
    """
    anim = getattr(obj, "animation_data", None)
    action = getattr(anim, "action", None) if anim is not None else None
    if action is None:
        return []

    flat = getattr(action, "fcurves", None)
    if flat:
        return list(flat)

    layers = getattr(action, "layers", None)
    if not layers:
        return []
    slot = getattr(anim, "action_slot", None)
    out: list[Any] = []
    for layer in layers:
        for strip in getattr(layer, "strips", []) or []:
            channelbag = getattr(strip, "channelbag", None)
            if not callable(channelbag):
                continue
            try:
                cb = channelbag(slot) if slot is not None else None
            except (TypeError, RuntimeError):
                cb = None
            if cb is not None:
                out.extend(getattr(cb, "fcurves", []) or [])
    return out


def set_interpolation(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    interpolation = str(payload.get("interpolation", "BEZIER"))
    fcurves = _fcurves(obj)
    if not fcurves:
        raise BridgeError(
            PRECONDITION,
            f"object '{obj.name}' has no animation f-curves to set interpolation on",
            {"object": obj.name},
        )
    keys_changed = 0
    for fcurve in fcurves:
        for point in getattr(fcurve, "keyframe_points", []) or []:
            point.interpolation = interpolation
            keys_changed += 1
        if hasattr(fcurve, "update"):
            fcurve.update()
    return {
        "object": obj.name,
        "interpolation": interpolation,
        "fcurves": len(fcurves),
        "keyframes": keys_changed,
    }


def list_actions(ctx: Ctx, payload: dict) -> dict:
    actions = list(getattr(ctx.bpy.data, "actions", []) or [])
    out = []
    for action in actions:
        frame_range = getattr(action, "frame_range", None)
        out.append(
            {
                "name": getattr(action, "name", "?"),
                "fcurves": len(list(getattr(action, "fcurves", []) or [])),
                "frame_range": [float(v) for v in frame_range] if frame_range is not None else None,
            }
        )
    return {"count": len(out), "actions": out}


def report(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    fcurves = _fcurves(obj)
    keyframes = sum(len(list(getattr(fc, "keyframe_points", []) or [])) for fc in fcurves)

    anim = getattr(obj, "animation_data", None)
    action = getattr(anim, "action", None) if anim is not None else None
    action_name = getattr(action, "name", None) if action is not None else None
    frame_range = getattr(action, "frame_range", None) if action is not None else None

    return {
        "object": obj.name,
        "action": action_name,
        "frame_range": [float(v) for v in frame_range] if frame_range is not None else None,
        "fcurves": len(fcurves),
        "keyframes": keyframes,
    }


COMMANDS = [
    Command("anim.set_frame", set_frame, mutates=True, feedback="viewport"),
    Command("anim.insert_keyframe", insert_keyframe, mutates=True, feedback="viewport"),
    Command("anim.delete_keyframe", delete_keyframe, mutates=True, feedback="viewport"),
    Command("anim.set_interpolation", set_interpolation, mutates=True, feedback="viewport"),
    Command("anim.list_actions", list_actions, mutates=False),
    Command("anim.report", report, mutates=False),
]
