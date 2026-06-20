"""Object domain manifest: lifecycle, transforms, origins, and bounds."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="object.transform_get",
        category="object",
        summary="Read an object's transform state",
        command="object.transform_get",
        params={"object": Str(required=True, summary="Object name")},
    ),
    ToolSpec(
        name="object.bounds",
        category="object",
        summary="Read an object's local and world bounds",
        command="object.bounds",
        params={"object": Str(required=True, summary="Object name")},
    ),
]
