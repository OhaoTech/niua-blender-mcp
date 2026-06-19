"""Feedback domain manifest: the agent's eyes."""

from __future__ import annotations

from ..kernel import Enum, ToolSpec

SPECS = [
    ToolSpec(
        name="feedback.capture",
        category="feedback",
        summary="Render the current view to a PNG the agent can see",
        command="feedback.capture",
        params={"mode": Enum(["viewport"], default="viewport", summary="Capture mode")},
    ),
]
