"""Video Sequencer GUI-parity handlers."""

from __future__ import annotations

import json
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _scene(ctx: Ctx) -> Any:
    return ctx.bpy.context.scene


def _editor(scene: Any, *, create: bool = True) -> Any:
    editor = getattr(scene, "sequence_editor", None)
    if editor is None and create:
        creator = getattr(scene, "sequence_editor_create", None)
        if not callable(creator):
            raise BridgeError(PRECONDITION, "scene cannot create a sequence editor")
        editor = creator()
    if editor is None:
        raise BridgeError(NOT_FOUND, "scene has no sequence editor")
    return editor


def _strips(editor: Any) -> Any:
    strips = getattr(editor, "strips", None)
    if strips is None:
        strips = getattr(editor, "sequences", None)
    if strips is None:
        raise BridgeError(PRECONDITION, "sequence editor does not expose strips")
    return strips


def _strip_list(editor: Any) -> list[Any]:
    return list(_strips(editor) or [])


def _get_strip(editor: Any, name: Any) -> Any:
    strip_name = _require_name(name, "strip name")
    strips = _strips(editor)
    getter = getattr(strips, "get", None)
    strip = getter(strip_name) if callable(getter) else None
    if strip is None:
        strip = next((candidate for candidate in _strip_list(editor) if getattr(candidate, "name", None) == strip_name), None)
    if strip is None:
        raise BridgeError(NOT_FOUND, f"strip not found: {strip_name}")
    return strip


def _index_of(editor: Any, strip: Any) -> int:
    for index, candidate in enumerate(_strip_list(editor)):
        if candidate is strip or getattr(candidate, "name", None) == getattr(strip, "name", None):
            return index
    return -1


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


def _iter_rna_props(owner: Any) -> list[Any]:
    return list(getattr(getattr(owner, "bl_rna", None), "properties", []) or [])


def _rna_prop(owner: Any, identifier: str) -> Any | None:
    for prop in _iter_rna_props(owner):
        if getattr(prop, "identifier", "") == identifier:
            return prop
    return None


def _properties_report(owner: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prop in _iter_rna_props(owner):
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
            entry["value"] = _jsonable(getattr(owner, identifier))
            entry["readable"] = True
        except Exception as exc:  # noqa: BLE001 - some strip RNA can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _compact_strip(editor: Any, strip: Any) -> dict[str, Any]:
    return {
        "index": _index_of(editor, strip),
        "name": getattr(strip, "name", ""),
        "type": getattr(strip, "type", None),
        "channel": int(getattr(strip, "channel", 0) or 0),
        "frame_start": int(getattr(strip, "frame_start", 0) or 0),
        "frame_final_end": int(getattr(strip, "frame_final_end", 0) or 0),
        "mute": bool(getattr(strip, "mute", False)),
        "blend_type": getattr(strip, "blend_type", None),
        "modifier_count": len(_modifier_list(strip)),
    }


def _strip_report(editor: Any, strip: Any) -> dict[str, Any]:
    out = _compact_strip(editor, strip)
    out["properties"] = _properties_report(strip)
    out["modifiers"] = [_modifier_report(modifier, index) for index, modifier in enumerate(_modifier_list(strip))]
    return out


def _report_payload(scene: Any) -> dict[str, Any]:
    editor = _editor(scene, create=False)
    strips = [_strip_report(editor, strip) for strip in _strip_list(editor)]
    return {"scene": getattr(scene, "name", ""), "strip_count": len(strips), "strips": strips}


def _modifier_list(strip: Any) -> list[Any]:
    return list(getattr(strip, "modifiers", []) or [])


def _get_modifier(strip: Any, name: Any) -> Any:
    modifier_name = _require_name(name, "modifier name")
    modifiers = getattr(strip, "modifiers", None)
    getter = getattr(modifiers, "get", None)
    modifier = getter(modifier_name) if callable(getter) else None
    if modifier is None:
        modifier = next((candidate for candidate in _modifier_list(strip) if getattr(candidate, "name", None) == modifier_name), None)
    if modifier is None:
        raise BridgeError(NOT_FOUND, f"strip modifier not found: {modifier_name}", {"strip": getattr(strip, "name", "?")})
    return modifier


def _modifier_report(modifier: Any, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "name": getattr(modifier, "name", ""),
        "type": getattr(modifier, "type", None),
        "mute": bool(getattr(modifier, "mute", False)),
        "properties": _properties_report(modifier),
    }


def _modifiers_payload(strip: Any) -> dict[str, Any]:
    modifiers = [_modifier_report(modifier, index) for index, modifier in enumerate(_modifier_list(strip))]
    return {"strip": getattr(strip, "name", ""), "modifier_count": len(modifiers), "modifiers": modifiers}


def _parse_json(raw: Any) -> Any:
    if not isinstance(raw, str):
        raise BridgeError(INVALID_PARAMS, "value must be a JSON-encoded string")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise BridgeError(INVALID_PARAMS, f"value is not valid JSON: {exc}") from exc


def _coerce_value(current: Any, value: Any) -> Any:
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


def _set_property(owner: Any, path: str, raw_value: Any) -> dict[str, Any]:
    attr = _require_name(path, "property")
    if not hasattr(owner, attr):
        raise BridgeError(INVALID_PARAMS, f"property not found: {attr}")
    prop = _rna_prop(owner, attr)
    if prop is not None and bool(getattr(prop, "is_readonly", False)):
        raise BridgeError(PRECONDITION, f"property is read-only: {attr}")
    value = _coerce_value(getattr(owner, attr), _parse_json(raw_value))
    try:
        setattr(owner, attr, value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise BridgeError(INVALID_PARAMS, f"could not set {attr}: {exc}") from exc
    return {"property": attr, "value": _jsonable(getattr(owner, attr))}


def report(ctx: Ctx, payload: dict) -> dict:
    return _report_payload(_scene(ctx))


def strip_add(ctx: Ctx, payload: dict) -> dict:
    scene = _scene(ctx)
    editor = _editor(scene, create=True)
    strips = _strips(editor)
    strip_type = str(payload.get("type", "")).upper()
    if not strip_type:
        raise BridgeError(PRECONDITION, "type is required")
    name = payload.get("name")
    label = name if isinstance(name, str) and name else strip_type
    frame_start = int(payload.get("frame_start", 1))
    channel = int(payload.get("channel", 1))
    path = payload.get("path")
    try:
        if strip_type == "MOVIE" and isinstance(path, str) and path:
            strip = strips.new_movie(name=label, filepath=path, channel=channel, frame_start=frame_start)
        elif strip_type == "SOUND" and isinstance(path, str) and path:
            strip = strips.new_sound(name=label, filepath=path, channel=channel, frame_start=frame_start)
        else:
            length = max(1, int(getattr(scene, "frame_end", frame_start) or frame_start) - frame_start + 1)
            strip = strips.new_effect(name=label, type=strip_type, channel=channel, frame_start=frame_start, length=length)
    except Exception as exc:  # noqa: BLE001 - Blender raises TypeError/RuntimeError for unsupported strip types
        raise BridgeError(INVALID_PARAMS, f"could not add strip of type {strip_type}: {exc}") from exc
    return {"scene": getattr(scene, "name", ""), "strip": _strip_report(editor, strip)}


def strip_remove(ctx: Ctx, payload: dict) -> dict:
    scene = _scene(ctx)
    editor = _editor(scene, create=False)
    strip = _get_strip(editor, payload.get("name"))
    _strips(editor).remove(strip)
    return _report_payload(scene)


def strip_set(ctx: Ctx, payload: dict) -> dict:
    scene = _scene(ctx)
    editor = _editor(scene, create=False)
    strip = _get_strip(editor, payload.get("name"))
    change = _set_property(strip, payload.get("property"), payload.get("value"))
    return {"scene": getattr(scene, "name", ""), **change, "strip": _strip_report(editor, strip)}


def modifiers(ctx: Ctx, payload: dict) -> dict:
    editor = _editor(_scene(ctx), create=False)
    return _modifiers_payload(_get_strip(editor, payload.get("name")))


def modifier_add(ctx: Ctx, payload: dict) -> dict:
    scene = _scene(ctx)
    editor = _editor(scene, create=False)
    strip = _get_strip(editor, payload.get("name"))
    modifier_type = str(payload.get("type", "")).upper()
    if not modifier_type:
        raise BridgeError(PRECONDITION, "type is required")
    before = set(id(modifier) for modifier in _modifier_list(strip))
    if hasattr(editor, "active_strip"):
        editor.active_strip = strip
    if hasattr(strip, "select"):
        strip.select = True
    with ctx.ensure(area="SEQUENCE_EDITOR"):
        op = ctx.bpy.ops.sequencer.strip_modifier_add
        ctx.check_poll(op)
        op(type=modifier_type)
    modifier = next((item for item in reversed(_modifier_list(strip)) if id(item) not in before), None)
    if modifier is None and _modifier_list(strip):
        modifier = _modifier_list(strip)[-1]
    if modifier is None:
        raise BridgeError(PRECONDITION, "no strip modifier was created")
    name = payload.get("modifier_name")
    if isinstance(name, str) and name:
        modifier.name = name
    return {"strip": getattr(strip, "name", ""), "modifier": _modifier_report(modifier, _modifier_list(strip).index(modifier))}


def modifier_set(ctx: Ctx, payload: dict) -> dict:
    editor = _editor(_scene(ctx), create=False)
    strip = _get_strip(editor, payload.get("name"))
    modifier = _get_modifier(strip, payload.get("modifier"))
    change = _set_property(modifier, payload.get("property"), payload.get("value"))
    return {"strip": getattr(strip, "name", ""), **change, "modifier": _modifier_report(modifier, _modifier_list(strip).index(modifier))}


def modifier_remove(ctx: Ctx, payload: dict) -> dict:
    editor = _editor(_scene(ctx), create=False)
    strip = _get_strip(editor, payload.get("name"))
    modifier = _get_modifier(strip, payload.get("modifier"))
    strip.modifiers.remove(modifier)
    return _modifiers_payload(strip)


COMMANDS = [
    Command("sequencer.report", report, mutates=False),
    Command("sequencer.strip_add", strip_add, mutates=True, feedback="viewport"),
    Command("sequencer.strip_remove", strip_remove, mutates=True, feedback="viewport"),
    Command("sequencer.strip_set", strip_set, mutates=True, feedback="viewport"),
    Command("sequencer.modifiers", modifiers, mutates=False),
    Command("sequencer.modifier_add", modifier_add, mutates=True, feedback="viewport"),
    Command("sequencer.modifier_set", modifier_set, mutates=True, feedback="viewport"),
    Command("sequencer.modifier_remove", modifier_remove, mutates=True, feedback="viewport"),
]
