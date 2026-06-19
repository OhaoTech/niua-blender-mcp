"""Session domain manifest: safe iteration beyond a single undo step.

The critique loop's safe-iterate primitive. ``checkpoint`` snapshots an object's data +
transform (a non-destructive datablock copy, so ``mutates=False``); ``revert`` swaps that
snapshot back (``mutates=True``, one undo step); ``list_checkpoints`` is read-only. The
agent's recipe: checkpoint -> edit -> ``feedback.critique`` -> keep or revert -> repeat.
Snapshots live in a dedicated store, independent of Blender's fragile, human-shared undo
stack.
"""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="session.checkpoint",
        category="session",
        summary="Snapshot an object's mesh data + transform so an edit can be rolled back",
        command="session.checkpoint",
        params={
            "object": Str(summary="Object to snapshot (defaults to active)"),
            "label": Str(summary="Checkpoint label (auto-generated if omitted)"),
        },
    ),
    ToolSpec(
        name="session.revert",
        category="session",
        summary="Restore an object from a checkpoint (most recent if no label); one undo step",
        command="session.revert",
        params={
            "object": Str(summary="Object to restore (defaults to active)"),
            "label": Str(summary="Checkpoint label to restore (defaults to most recent)"),
        },
        mutates=True,
    ),
    ToolSpec(
        name="session.list_checkpoints",
        category="session",
        summary="List stored checkpoints for an object, or all objects (read-only)",
        command="session.list_checkpoints",
        params={
            "object": Str(summary="Object to list checkpoints for (all objects if omitted)"),
        },
    ),
]
