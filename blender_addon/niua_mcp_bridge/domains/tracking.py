"""Tracking / Clip Editor GUI-parity handlers."""

from __future__ import annotations

import os
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError

_TRACK_REPORT_LIMIT = 256
_MARKER_REPORT_LIMIT = 512


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _require_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(INVALID_PARAMS, "path is required")
    path = os.path.abspath(os.path.expanduser(value))
    if not os.path.exists(path):
        raise BridgeError(INVALID_PARAMS, f"path does not exist: {value}")
    return path


def _items(value: Any) -> list[Any]:
    try:
        return list(value or [])
    except TypeError:
        return []


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in value]
    except TypeError:
        return []


def _nested_float_list(value: Any) -> list[list[float]]:
    try:
        return [_float_list(item) for item in value]
    except TypeError:
        return []


def _movieclips(ctx: Ctx) -> list[Any]:
    return _items(getattr(getattr(ctx.bpy, "data", None), "movieclips", []))


def _require_clip(ctx: Ctx, name: Any) -> Any:
    clip_name = _require_name(name, "clip")
    clip = getattr(ctx.bpy.data.movieclips, "get", lambda _name: None)(clip_name)
    if clip is None:
        raise BridgeError(NOT_FOUND, f"movie clip not found: {clip_name}")
    return clip


def _iter_rna_props(owner: Any) -> list[Any]:
    return list(getattr(getattr(owner, "bl_rna", None), "properties", []) or [])


def _rna_prop(owner: Any, identifier: str) -> Any | None:
    properties = getattr(getattr(owner, "bl_rna", None), "properties", None)
    if properties is not None:
        try:
            return properties[identifier]
        except (KeyError, TypeError, AttributeError):
            getter = getattr(properties, "get", None)
            prop = getter(identifier) if callable(getter) else None
            if prop is not None:
                return prop
    for prop in _iter_rna_props(owner):
        if getattr(prop, "identifier", "") == identifier:
            return prop
    return None


def _enum_items(prop: Any) -> list[dict[str, str]]:
    items = list(getattr(prop, "enum_items", []) or [])
    if not items:
        items = list(getattr(prop, "enum_items_static", []) or [])
    return [
        {"identifier": str(getattr(item, "identifier", "")), "name": str(getattr(item, "name", ""))}
        for item in items
        if getattr(item, "identifier", "")
    ]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    name = getattr(value, "name", None)
    if name is not None or getattr(value, "bl_rna", None) is not None:
        out = {"name": str(name)} if name is not None else {"repr": repr(value)}
        value_type = getattr(value, "type", None)
        if value_type is not None:
            out["type"] = str(value_type)
        return out
    try:
        return [_jsonable(item) for item in value]
    except Exception:  # noqa: BLE001 - arbitrary RNA values may expose partial sequence APIs
        return repr(value)


def _collection_value(value: Any) -> dict[str, Any]:
    items = _items(value)
    sample = []
    for item in items[:20]:
        name = getattr(item, "name", None)
        sample.append(str(name) if name is not None else repr(item))
    return {"count": len(items), "items": sample, "truncated": len(items) > 20}


def _properties_report(owner: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for prop in _iter_rna_props(owner):
        identifier = str(getattr(prop, "identifier", "") or "")
        if not identifier or identifier == "rna_type":
            continue
        prop_type = str(getattr(prop, "type", "") or "")
        entry: dict[str, Any] = {
            "name": str(getattr(prop, "name", "") or identifier),
            "description": str(getattr(prop, "description", "") or ""),
            "type": prop_type,
            "subtype": str(getattr(prop, "subtype", "") or ""),
            "is_readonly": bool(getattr(prop, "is_readonly", False)),
            "is_array": bool(getattr(prop, "is_array", False)),
            "array_length": int(getattr(prop, "array_length", 0) or 0),
        }
        enum_items = _enum_items(prop)
        if enum_items:
            entry["enum_items"] = enum_items
        try:
            value = getattr(owner, identifier)
            entry["value"] = _collection_value(value) if prop_type == "COLLECTION" else _jsonable(value)
            entry["readable"] = True
        except Exception as exc:  # noqa: BLE001 - some RNA reads can be context dependent
            entry["readable"] = False
            entry["read_error"] = str(exc)
        out[identifier] = entry
    return out


def _tracks(clip: Any) -> list[Any]:
    tracking = getattr(clip, "tracking", None)
    return _items(getattr(tracking, "tracks", []))


def _marker_count(track: Any) -> int:
    return len(_items(getattr(track, "markers", [])))


def _clip_summary(clip: Any) -> dict[str, Any]:
    tracks = _tracks(clip)
    size = getattr(clip, "size", [])
    display_aspect = getattr(clip, "display_aspect", [])
    return {
        "name": getattr(clip, "name", ""),
        "filepath": getattr(clip, "filepath", ""),
        "size": [int(item) for item in _float_list(size)],
        "display_aspect": _float_list(display_aspect),
        "source": getattr(clip, "source", None),
        "frame_start": int(getattr(clip, "frame_start", 0) or 0),
        "frame_offset": int(getattr(clip, "frame_offset", 0) or 0),
        "frame_duration": int(getattr(clip, "frame_duration", 0) or 0),
        "fps": float(getattr(clip, "fps", 0.0) or 0.0),
        "track_count": len(tracks),
        "marker_count": sum(_marker_count(track) for track in tracks),
    }


def _marker_report(marker: Any) -> dict[str, Any]:
    return {
        "frame": int(getattr(marker, "frame", 0) or 0),
        "co": _float_list(getattr(marker, "co", [])),
        "mute": bool(getattr(marker, "mute", False)),
        "pattern_corners": _nested_float_list(getattr(marker, "pattern_corners", [])),
        "search_min": _float_list(getattr(marker, "search_min", [])),
        "search_max": _float_list(getattr(marker, "search_max", [])),
        "properties": _properties_report(marker),
    }


def _track_report(track: Any, include_markers: bool = True) -> dict[str, Any]:
    markers = _items(getattr(track, "markers", []))
    out = {
        "name": getattr(track, "name", ""),
        "select": bool(getattr(track, "select", False)),
        "lock": bool(getattr(track, "lock", False)),
        "mute": bool(getattr(track, "mute", False)),
        "hide": bool(getattr(track, "hide", False)),
        "use_custom_color": bool(getattr(track, "use_custom_color", False)),
        "color": _float_list(getattr(track, "color", [])),
        "average_error": float(getattr(track, "average_error", 0.0) or 0.0),
        "marker_count": len(markers),
        "properties": _properties_report(track),
    }
    if include_markers:
        out["markers"] = [_marker_report(marker) for marker in markers[:_MARKER_REPORT_LIMIT]]
        out["markers_truncated"] = len(markers) > _MARKER_REPORT_LIMIT
    return out


def _tracking_report(clip: Any) -> dict[str, Any]:
    tracking = getattr(clip, "tracking", None)
    tracks_owner = getattr(tracking, "tracks", None)
    active = getattr(tracks_owner, "active", None)
    return {
        "clip": getattr(clip, "name", ""),
        "active_track": getattr(active, "name", None),
        "track_count": len(_tracks(clip)),
        "tracks": [_track_report(track, include_markers=True) for track in _tracks(clip)[:_TRACK_REPORT_LIMIT]],
        "tracks_truncated": len(_tracks(clip)) > _TRACK_REPORT_LIMIT,
        "settings": _properties_report(getattr(tracking, "settings", None)),
        "camera": _properties_report(getattr(tracking, "camera", None)),
        "reconstruction": _properties_report(getattr(tracking, "reconstruction", None)),
        "stabilization": _properties_report(getattr(tracking, "stabilization", None)),
        "dopesheet": _properties_report(getattr(tracking, "dopesheet", None)),
    }


def _marker_payload(clip: Any) -> dict[str, Any]:
    tracks = _tracks(clip)
    payload_tracks = []
    marker_total = 0
    for track in tracks[:_TRACK_REPORT_LIMIT]:
        markers = _items(getattr(track, "markers", []))
        marker_total += len(markers)
        payload_tracks.append(
            {
                "name": getattr(track, "name", ""),
                "marker_count": len(markers),
                "markers": [_marker_report(marker) for marker in markers[:_MARKER_REPORT_LIMIT]],
                "markers_truncated": len(markers) > _MARKER_REPORT_LIMIT,
            }
        )
    return {
        "clip": getattr(clip, "name", ""),
        "track_count": len(tracks),
        "marker_count": marker_total,
        "tracks": payload_tracks,
        "tracks_truncated": len(tracks) > _TRACK_REPORT_LIMIT,
    }


def _assign_clip_to_editors(ctx: Ctx, clip: Any) -> int:
    count = 0
    wm = getattr(getattr(ctx.bpy, "context", None), "window_manager", None)
    for window in _items(getattr(wm, "windows", [])):
        screen = getattr(window, "screen", None)
        for area in _items(getattr(screen, "areas", [])):
            if getattr(area, "type", None) != "CLIP_EDITOR":
                continue
            for space in _items(getattr(area, "spaces", [])):
                if getattr(space, "type", None) == "CLIP_EDITOR" and hasattr(space, "clip"):
                    space.clip = clip
                    count += 1
    return count


def report(ctx: Ctx, payload: dict) -> dict:
    clips = _movieclips(ctx)
    return {
        "clip_count": len(clips),
        "clips": [_clip_summary(clip) for clip in clips],
    }


def clip_load(ctx: Ctx, payload: dict) -> dict:
    path = _require_path(payload.get("path"))
    try:
        clip = ctx.bpy.data.movieclips.load(path, check_existing=True)
    except TypeError:
        clip = ctx.bpy.data.movieclips.load(path)
    name = payload.get("name")
    if isinstance(name, str) and name:
        clip.name = name
    assigned = _assign_clip_to_editors(ctx, clip)
    return {"clip": _clip_summary(clip), "assigned_clip_editors": assigned}


def clips(ctx: Ctx, payload: dict) -> dict:
    clip_list = _movieclips(ctx)
    return {"clip_count": len(clip_list), "clips": [_clip_summary(clip) for clip in clip_list]}


def marker_report(ctx: Ctx, payload: dict) -> dict:
    return _marker_payload(_require_clip(ctx, payload.get("clip")))


def track_report(ctx: Ctx, payload: dict) -> dict:
    return _tracking_report(_require_clip(ctx, payload.get("clip")))


COMMANDS = [
    Command("tracking.report", report, mutates=False),
    Command("tracking.clip_load", clip_load, mutates=True, feedback="viewport"),
    Command("tracking.clips", clips, mutates=False),
    Command("tracking.marker_report", marker_report, mutates=False),
    Command("tracking.track_report", track_report, mutates=False),
]
