"""Animation domain manifest: keyframe animation (object mode).

Keyframes bind an object property (``data_path`` such as "location" or "rotation_euler")
to a value at a scene frame. ``anim.set_frame`` moves the playhead; ``anim.insert_keyframe``
/ ``anim.delete_keyframe`` add/remove keys; ``anim.set_interpolation`` rewrites the
interpolation of every keyframe point on the object's f-curves; ``anim.list_actions`` and
``anim.report`` are read-only feedback ("the eyes"): the actions in the file and the
object's frame range + f-curve/keyframe counts.
"""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="anim.set_frame",
        category="animation",
        summary="Set the current scene frame (playhead)",
        command="anim.set_frame",
        params={
            "frame": Int(required=True, summary="Frame number to set as current"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="anim.insert_keyframe",
        category="animation",
        summary="Insert a keyframe on an object property at a frame",
        command="anim.insert_keyframe",
        params={
            "object": Str(summary="Object to key (defaults to active)"),
            "data_path": Str(
                required=True, summary="Property path, e.g. 'location' or 'rotation_euler'"
            ),
            "frame": Int(summary="Frame to key (defaults to current scene frame)"),
            "index": Int(
                default=-1,
                summary="Array element index to key (-1 keys all components)",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="anim.delete_keyframe",
        category="animation",
        summary="Delete a keyframe on an object property at a frame",
        command="anim.delete_keyframe",
        params={
            "object": Str(summary="Object to edit (defaults to active)"),
            "data_path": Str(required=True, summary="Property path, e.g. 'location'"),
            "frame": Int(summary="Frame to delete (defaults to current scene frame)"),
            "index": Int(
                default=-1,
                summary="Array element index (-1 deletes all components)",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="anim.set_interpolation",
        category="animation",
        summary="Set interpolation for all keyframes on an object's f-curves",
        command="anim.set_interpolation",
        params={
            "object": Str(summary="Object whose f-curves to edit (defaults to active)"),
            "interpolation": Enum(
                ["CONSTANT", "LINEAR", "BEZIER"],
                required=True,
                summary="Interpolation mode applied to every keyframe point",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="anim.list_actions",
        category="animation",
        summary="List the actions in the file (read-only)",
        command="anim.list_actions",
        params={},
    ),
    ToolSpec(
        name="anim.report",
        category="animation",
        summary="Animation report for an object: frame range, f-curve count (read-only)",
        command="anim.report",
        params={
            "object": Str(summary="Object to inspect (defaults to active)"),
        },
    ),
]
