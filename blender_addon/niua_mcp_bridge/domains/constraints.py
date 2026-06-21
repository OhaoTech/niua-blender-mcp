"""Constraints GUI-parity handlers.

This domain owns the Properties editor's Constraint context. It covers both object
constraint stacks and armature pose-bone constraint stacks while keeping the older
``rig.constraint_*`` tools as rigging conveniences.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


@dataclass(frozen=True)
class _Stack:
    obj: Any
    owner: str
    bone: str | None
    constraints: Any
    mode: str


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _owner(value: Any) -> str:
    owner = str(value or "OBJECT").upper()
    if owner in {"OBJECT", "OBJECT_CONSTRAINT"}:
        return "OBJECT"
    if owner in {"BONE", "POSE", "POSE_BONE", "BONE_CONSTRAINT"}:
        return "BONE"
    raise BridgeError(INVALID_PARAMS, f"unsupported constraint owner: {owner}")


def _get_pose_bone(obj: Any, bone_name: Any) -> Any:
    bone = _require_name(bone_name, "bone")
    if getattr(obj, "type", None) != "ARMATURE":
        raise BridgeError(PRECONDITION, f"object is not an armature: {getattr(obj, 'name', '?')}")
    bones = getattr(getattr(obj, "pose", None), "bones", None)
    getter = getattr(bones, "get", None)
    pose_bone = getter(bone) if callable(getter) else None
    if pose_bone is None:
        pose_bone = next((candidate for candidate in list(bones or []) if getattr(candidate, "name", None) == bone), None)
    if pose_bone is None:
        raise BridgeError(NOT_FOUND, f"pose bone not found: {bone}", {"object": getattr(obj, "name", "?")})
    return pose_bone


def _resolve_stack(ctx: Ctx, payload: dict) -> _Stack:
    obj = ctx.get_object(_require_name(payload.get("object"), "object"))
    owner = _owner(payload.get("owner"))
    if owner == "OBJECT":
        constraints = getattr(obj, "constraints", None)
        if constraints is None:
            raise BridgeError(PRECONDITION, f"object does not expose constraints: {getattr(obj, 'name', '?')}")
        return _Stack(obj=obj, owner="OBJECT", bone=None, constraints=constraints, mode="OBJECT")

    pose_bone = _get_pose_bone(obj, payload.get("bone"))
    constraints = getattr(pose_bone, "constraints", None)
    if constraints is None:
        raise BridgeError(PRECONDITION, f"pose bone does not expose constraints: {getattr(pose_bone, 'name', '?')}")
    return _Stack(obj=obj, owner="BONE", bone=getattr(pose_bone, "name", str(payload.get("bone"))), constraints=constraints, mode="POSE")


def _constraint_list(stack: _Stack) -> list[Any]:
    return list(stack.constraints or [])


def _get_constraint(stack: _Stack, name: Any) -> Any:
    constraint_name = _require_name(name, "constraint name")
    getter = getattr(stack.constraints, "get", None)
    constraint = getter(constraint_name) if callable(getter) else None
    if constraint is None:
        constraint = next((candidate for candidate in _constraint_list(stack) if getattr(candidate, "name", None) == constraint_name), None)
    if constraint is None:
        raise BridgeError(NOT_FOUND, f"constraint not found: {constraint_name}", {"object": getattr(stack.obj, "name", "?")})
    return constraint


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    name = getattr(value, "name", None)
    if name is not None:
        out = {"name": str(name)}
        value_type = getattr(value, "type", None)
        if value_type is not None:
            out["type"] = str(value_type)
        return out
    try:
        return [_jsonable(item) for item in value]
    except Exception:  # noqa: BLE001 - arbitrary RNA values may expose partial sequence APIs
        return repr(value)


def _compact_constraint(constraint: Any, index: int) -> dict[str, Any]:
    target = getattr(constraint, "target", None)
    return {
        "index": index,
        "name": getattr(constraint, "name", ""),
        "type": getattr(constraint, "type", None),
        "influence": float(getattr(constraint, "influence", 0.0) or 0.0),
        "mute": bool(getattr(constraint, "mute", False)),
        "target": getattr(target, "name", None) if target is not None else None,
        "subtarget": getattr(constraint, "subtarget", ""),
    }


def _iter_rna_props(owner: Any) -> list[Any]:
    return list(getattr(getattr(owner, "bl_rna", None), "properties", []) or [])


def _rna_prop(owner: Any, identifier: str) -> Any | None:
    for prop in _iter_rna_props(owner):
        if getattr(prop, "identifier", "") == identifier:
            return prop
    return None


def _constraint_report(constraint: Any, index: int) -> dict[str, Any]:
    out = _compact_constraint(constraint, index)
    properties: dict[str, Any] = {}
    for prop in _iter_rna_props(constraint):
        identifier = str(getattr(prop, "identifier", "") or "")
        if not identifier or identifier == "rna_type":
            continue
        entry: dict[str, Any] = {
            "name": str(getattr(prop, "name", "") or identifier),
            "description": str(getattr(prop, "description", "") or ""),
            "type": str(getattr(prop, "type", "") or ""),
            "subtype": str(getattr(prop, "subtype", "") or ""),
            "is_readonly": bool(getattr(prop, "is_readonly", False)),
            "is_array": bool(getattr(prop, "is_array", False)),
            "array_length": int(getattr(prop, "array_length", 0) or 0),
        }
        enum_items = [
            {"identifier": str(getattr(item, "identifier", "")), "name": str(getattr(item, "name", ""))}
            for item in list(getattr(prop, "enum_items", []) or [])
            if getattr(item, "identifier", "")
        ]
        if enum_items:
            entry["enum_items"] = enum_items
        try:
            entry["value"] = _jsonable(getattr(constraint, identifier))
            entry["readable"] = True
        except Exception as exc:  # noqa: BLE001 - some constraint RNA can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        properties[identifier] = entry
    out["properties"] = properties
    return out


def _stack_header(stack: _Stack) -> dict[str, Any]:
    return {"object": stack.obj.name, "owner": stack.owner, "bone": stack.bone}


def _list_payload(stack: _Stack) -> dict[str, Any]:
    constraints = [_compact_constraint(constraint, index) for index, constraint in enumerate(_constraint_list(stack))]
    return {**_stack_header(stack), "constraint_count": len(constraints), "constraints": constraints}


def _report_payload(stack: _Stack, name: Any = "") -> dict[str, Any]:
    if isinstance(name, str) and name:
        constraint = _get_constraint(stack, name)
        index = _constraint_list(stack).index(constraint)
        return {**_stack_header(stack), "constraint": _constraint_report(constraint, index)}
    constraints = [_constraint_report(constraint, index) for index, constraint in enumerate(_constraint_list(stack))]
    return {**_stack_header(stack), "constraint_count": len(constraints), "constraints": constraints}


def _parse_json(raw: Any) -> Any:
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "value must be a JSON-encoded string")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise BridgeError(INVALID_PARAMS, f"value is not valid JSON: {exc}") from exc


def _coerce_value(ctx: Ctx, current: Any, value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("object"), str):
        return ctx.get_object(value["object"])
    if isinstance(current, bool):
        if isinstance(value, str):
            low = value.strip().lower()
            if low in {"true", "1", "yes", "on"}:
                return True
            if low in {"false", "0", "no", "off"}:
                return False
            raise BridgeError(INVALID_PARAMS, f"expected boolean value, got: {value!r}")
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value) if not isinstance(value, (list, tuple)) else value
    if isinstance(current, float):
        return float(value) if not isinstance(value, (list, tuple)) else value
    return value


def list_constraints(ctx: Ctx, payload: dict) -> dict:
    return _list_payload(_resolve_stack(ctx, payload))


def add(ctx: Ctx, payload: dict) -> dict:
    stack = _resolve_stack(ctx, payload)
    constraint_type = str(payload.get("type", "")).upper()
    if not constraint_type:
        raise BridgeError(PRECONDITION, "constraint type is required")
    with ctx.ensure(active=stack.obj, mode=stack.mode, select=[stack.obj]):
        try:
            constraint = stack.constraints.new(type=constraint_type)
        except Exception as exc:  # noqa: BLE001 - Blender raises TypeError for unknown constraint types
            raise BridgeError(INVALID_PARAMS, f"unsupported constraint type: {constraint_type}", {"type": constraint_type}) from exc
        name = payload.get("name")
        if isinstance(name, str) and name:
            constraint.name = name
    index = _constraint_list(stack).index(constraint)
    return {**_stack_header(stack), "constraint": _compact_constraint(constraint, index)}


def remove(ctx: Ctx, payload: dict) -> dict:
    stack = _resolve_stack(ctx, payload)
    constraint = _get_constraint(stack, payload.get("name"))
    with ctx.ensure(active=stack.obj, mode=stack.mode, select=[stack.obj]):
        stack.constraints.remove(constraint)
    return _list_payload(stack)


def report(ctx: Ctx, payload: dict) -> dict:
    return _report_payload(_resolve_stack(ctx, payload), payload.get("name", ""))


def set_property(ctx: Ctx, payload: dict) -> dict:
    stack = _resolve_stack(ctx, payload)
    constraint = _get_constraint(stack, payload.get("name"))
    prop_name = _require_name(payload.get("property"), "property")
    if not hasattr(constraint, prop_name):
        raise BridgeError(INVALID_PARAMS, f"constraint has no property: {prop_name}")
    prop = _rna_prop(constraint, prop_name)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {prop_name}")
    value = _coerce_value(ctx, getattr(constraint, prop_name), _parse_json(payload.get("value")))
    with ctx.ensure(active=stack.obj, mode=stack.mode, select=[stack.obj]):
        try:
            setattr(constraint, prop_name, value)
        except (TypeError, ValueError, AttributeError) as exc:
            raise BridgeError(INVALID_PARAMS, f"could not set {prop_name}: {exc}") from exc
    new_name = getattr(constraint, "name", "")
    index = _constraint_list(stack).index(constraint)
    return {
        **_stack_header(stack),
        "name": new_name,
        "property": prop_name,
        "value": _jsonable(getattr(constraint, prop_name)),
        "constraint": _constraint_report(constraint, index),
    }


COMMANDS = [
    Command("constraints.list", list_constraints, mutates=False),
    Command("constraints.add", add, mutates=True, feedback="viewport"),
    Command("constraints.remove", remove, mutates=True, feedback="viewport"),
    Command("constraints.report", report, mutates=False),
    Command("constraints.set", set_property, mutates=True, feedback="viewport"),
]
