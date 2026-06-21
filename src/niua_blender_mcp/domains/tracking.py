"""Tracking / Clip Editor GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="tracking.report",
        category="tracking",
        summary="Report MovieClip and tracking state",
        command="tracking.report",
        params={},
    ),
    ToolSpec(
        name="tracking.clip_load",
        category="tracking",
        summary="Load a movie clip or image sequence source",
        command="tracking.clip_load",
        params={
            "path": Str(required=True, summary="Clip file path"),
            "name": Str(default="", summary="Optional clip name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="tracking.clips",
        category="tracking",
        summary="List loaded movie clips",
        command="tracking.clips",
        params={},
    ),
    ToolSpec(
        name="tracking.marker_report",
        category="tracking",
        summary="Report markers for each track in a clip",
        command="tracking.marker_report",
        params={"clip": Str(required=True, summary="MovieClip name")},
    ),
    ToolSpec(
        name="tracking.track_report",
        category="tracking",
        summary="Report tracks for a clip",
        command="tracking.track_report",
        params={"clip": Str(required=True, summary="MovieClip name")},
    ),
]
