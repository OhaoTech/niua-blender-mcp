"""Session checkpoints: safe iteration beyond a single undo step.

The critique loop's safety primitive. Blender's undo stack is fragile across the kind of
multi-step, mode-switching edits an agent makes (and it is shared with the watching
human's Ctrl+Z), so we do NOT lean on it for "try an edit, judge it, roll back if it got
worse." Instead we snapshot the object's *data* and *transform* into a module-level store
and restore from there on demand.

A checkpoint stores:

* ``data`` -- a copy of the object's mesh/curve datablock (``obj.data.copy()``). Copying a
  datablock is non-destructive and does not change the visible scene, so ``checkpoint`` is
  ``mutates=False``.
* ``matrix_world`` + ``location`` / ``rotation_euler`` / ``scale`` -- the transform, as
  plain nested lists so a later restore is independent of any live matrix object.

Reverting swaps a *fresh copy* of the stored datablock back onto the object (a fresh copy
each time so the stored snapshot can be reverted to repeatedly) and restores the
transform. That mutates the visible scene, so ``revert`` is ``mutates=True`` (one undo
step).

The store is keyed ``object_name -> {label: snapshot}`` and lives at module scope so it
survives across dispatch calls within a running add-on session. It is importable without
``bpy`` (no bpy at module top) so it can be unit-tested under a fake bpy.
"""

from __future__ import annotations

import time
from typing import Any

#: object_name -> {label -> snapshot dict}. Insertion order of the inner dict is the
#: chronological order of checkpoints, which "most recent" relies on.
_STORE: dict[str, "dict[str, dict[str, Any]]"] = {}


def reset() -> None:
    """Drop every stored checkpoint (used by tests for isolation)."""
    _STORE.clear()


def _matrix_to_lists(matrix: Any) -> Any:
    """A 4x4 matrix (or any transform) as nested plain lists, or None."""
    if matrix is None:
        return None
    try:
        return [list(row) for row in matrix]
    except TypeError:
        return None


def _seq_to_list(seq: Any) -> Any:
    if seq is None:
        return None
    try:
        return [float(v) for v in seq]
    except TypeError:
        return None


def checkpoint(obj: Any, label: str | None = None) -> dict[str, Any]:
    """Snapshot ``obj``'s data + transform under ``label`` (auto if omitted).

    Returns ``{object, label}``. Does not mutate the visible scene.
    """
    name = obj.name
    if not label:
        label = "cp_%d" % int(time.time() * 1000)
    data = obj.data
    snapshot = {
        "label": label,
        "data": data.copy() if data is not None and hasattr(data, "copy") else None,
        "matrix_world": _matrix_to_lists(getattr(obj, "matrix_world", None)),
        "location": _seq_to_list(getattr(obj, "location", None)),
        "rotation_euler": _seq_to_list(getattr(obj, "rotation_euler", None)),
        "scale": _seq_to_list(getattr(obj, "scale", None)),
    }
    _STORE.setdefault(name, {})[label] = snapshot
    return {"object": name, "label": label}


def list_checkpoints(obj_name: str | None = None) -> list[dict[str, Any]]:
    """Read-only list of stored checkpoints, oldest first.

    For one object when ``obj_name`` is given, else across every object.
    """
    out: list[dict[str, Any]] = []
    names = [obj_name] if obj_name else list(_STORE.keys())
    for name in names:
        for label in _STORE.get(name, {}):
            out.append({"object": name, "label": label})
    return out


def _most_recent_label(obj_name: str) -> str | None:
    labels = _STORE.get(obj_name)
    if not labels:
        return None
    return next(reversed(labels))  # last inserted = most recent


def get_snapshot(obj_name: str, label: str | None = None) -> dict[str, Any] | None:
    """Return the stored snapshot for ``obj_name`` (most recent if ``label`` omitted)."""
    labels = _STORE.get(obj_name)
    if not labels:
        return None
    if label is None:
        label = _most_recent_label(obj_name)
    return labels.get(label) if label is not None else None


def restore(obj: Any, snapshot: dict[str, Any]) -> None:
    """Swap a fresh copy of the snapshot datablock onto ``obj`` and restore transform.

    A *fresh* copy each time keeps the stored snapshot intact for repeated reverts.
    """
    stored_data = snapshot.get("data")
    if stored_data is not None and hasattr(stored_data, "copy"):
        obj.data = stored_data.copy()
    elif stored_data is not None:
        obj.data = stored_data
    loc = snapshot.get("location")
    if loc is not None:
        obj.location = loc
    rot = snapshot.get("rotation_euler")
    if rot is not None:
        obj.rotation_euler = rot
    scl = snapshot.get("scale")
    if scl is not None:
        obj.scale = scl
    mw = snapshot.get("matrix_world")
    if mw is not None:
        obj.matrix_world = mw
