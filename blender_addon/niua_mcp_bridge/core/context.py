"""Context resolver: the keystone that makes operators runnable on demand.

RNA tells us an operator's *parameters* but not the *context* it needs: an active
object, a selection, an interaction mode (OBJECT/EDIT/SCULPT), and the right editor
area for ``bpy.ops`` polling and ``temp_override``. This module sets that context up,
runs the body, and restores everything afterward, so domain handlers never touch
context plumbing -- they just do::

    with ctx.ensure(active="Cube", mode="EDIT", select=["Cube"]):
        ctx.bpy.ops.mesh.subdivide()

It also exposes ``check_poll`` to turn a failing operator ``poll()`` into a clean
``precondition_failed`` error instead of a raw ``RuntimeError`` deep inside ``bpy.ops``.

``bpy`` is imported lazily inside methods (never at module top) so this module -- and
everything that imports it -- stays importable under fake-bpy unit tests.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..errors import PRECONDITION, BridgeError


class PreconditionError(BridgeError):
    """An operator's preconditions were not met (clean, not a raw RuntimeError)."""

    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(PRECONDITION, message, detail)


def _resolve_object(bpy: Any, ref: Any) -> Any:
    """Accept an object name (str) or an object datablock; return the datablock."""
    if ref is None:
        return None
    if isinstance(ref, str):
        obj = bpy.data.objects.get(ref)
        if obj is None:
            raise PreconditionError(f"object not found: {ref}")
        return obj
    return ref


def _find_area(bpy: Any, area_type: str) -> tuple[Any, Any, Any]:
    """Best-effort: return (window, area, region) for the first area of ``area_type``.

    Returns (None, None, None) when no such area exists (e.g. headless / background),
    in which case callers skip ``temp_override`` and run in the default context.
    """
    wm = getattr(bpy.context, "window_manager", None)
    windows = list(getattr(wm, "windows", []) or [])
    for window in windows:
        screen = getattr(window, "screen", None)
        for area in getattr(screen, "areas", []) or []:
            if getattr(area, "type", None) == area_type:
                region = next(
                    (r for r in getattr(area, "regions", []) or [] if getattr(r, "type", None) == "WINDOW"),
                    None,
                )
                return window, area, region
    return None, None, None


class ResolvedContext:
    """Context manager that temporarily sets active/selection/mode/area and restores it."""

    def __init__(
        self,
        active: Any = None,
        mode: str | None = None,
        area: str = "VIEW_3D",
        select: Iterable[Any] | None = None,
    ) -> None:
        self._active = active
        self._mode = mode.upper() if isinstance(mode, str) else mode
        self._area = area
        self._select = select
        # Saved state, populated on __enter__.
        self._bpy: Any = None
        self._prev_active: Any = None
        self._prev_selected: list[Any] = []
        self._prev_mode: str | None = None
        self._override = None  # an active temp_override CM, if any

    # -- helpers -----------------------------------------------------------------

    def _set_active(self, bpy: Any, obj: Any) -> None:
        # Accept an object datablock (enter path) or a name (restore path). A name that no longer
        # resolves -- because the wrapped operator removed the object (e.g. object.join/delete) --
        # is skipped rather than assigning a freed datablock.
        if isinstance(obj, str):
            objects = getattr(getattr(bpy, "data", None), "objects", None)
            obj = objects.get(obj) if hasattr(objects, "get") else None
            if obj is None:
                return
        view_layer = getattr(bpy.context, "view_layer", None)
        if view_layer is not None and hasattr(view_layer, "objects"):
            view_layer.objects.active = obj

    def _set_selection(self, bpy: Any, objects: list[Any]) -> None:
        # Accept object datablocks (enter path) or names (restore path). Objects the wrapped
        # operator removed are skipped -- reading ``.name`` off a freed datablock raises
        # "StructRNA of type Object has been removed".
        names: set = set()
        for o in objects:
            if isinstance(o, str):
                names.add(o)
                continue
            try:
                names.add(o.name)
            except ReferenceError:
                continue
        scene = getattr(bpy.context, "scene", None)
        for o in list(getattr(scene, "objects", []) or []):
            if hasattr(o, "select_set"):
                o.select_set(getattr(o, "name", None) in names)

    def _set_mode(self, bpy: Any, mode: str) -> None:
        # Mode is global per active object; object.mode_set is the supported switch.
        bpy.ops.object.mode_set(mode=mode)

    # -- context-manager protocol ------------------------------------------------

    def __enter__(self) -> "ResolvedContext":
        import bpy  # lazy: keeps the module importable without Blender

        self._bpy = bpy
        ctx = bpy.context

        # Snapshot current state so we can restore it.
        view_layer = getattr(ctx, "view_layer", None)
        # Snapshot prev active/selection by NAME (not datablock refs): if the wrapped operator
        # removes objects, restoring by name simply skips the gone ones instead of touching a
        # freed StructRNA on __exit__.
        prev_active = getattr(getattr(view_layer, "objects", None), "active", None)
        self._prev_active = getattr(prev_active, "name", None)
        self._prev_selected = [
            o.name
            for o in getattr(getattr(ctx, "scene", None), "objects", []) or []
            if getattr(o, "select_get", lambda: False)()
        ]
        self._prev_mode = getattr(getattr(ctx, "object", None), "mode", None)

        # Resolve + apply requested active object and selection.
        active_obj = _resolve_object(bpy, self._active)
        if self._select is not None:
            sel = [_resolve_object(bpy, s) for s in self._select]
            self._set_selection(bpy, sel)
        if active_obj is not None:
            self._set_active(bpy, active_obj)

        # Enter the area override if one is requested and available.
        if self._area:
            window, area, region = _find_area(bpy, self._area)
            if area is not None:
                override_kwargs: dict[str, Any] = {"area": area}
                if window is not None:
                    override_kwargs["window"] = window
                if region is not None:
                    override_kwargs["region"] = region
                self._override = bpy.context.temp_override(**override_kwargs)
                self._override.__enter__()

        # Switch interaction mode last (it needs the active object set above).
        if self._mode is not None and self._mode != self._prev_mode:
            self._set_mode(bpy, self._mode)

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        bpy = self._bpy
        # Restore mode before leaving the area override (mode_set needs a sane context).
        try:
            if self._mode is not None and self._prev_mode is not None and self._mode != self._prev_mode:
                self._set_mode(bpy, self._prev_mode)
        finally:
            if self._override is not None:
                self._override.__exit__(exc_type, exc, tb)
                self._override = None
            # Restore selection + active object.
            try:
                self._set_selection(bpy, self._prev_selected)
            finally:
                if self._prev_active is not None or self._active is not None:
                    self._set_active(bpy, self._prev_active)
        return False  # never swallow exceptions


def ensure(
    active: Any = None,
    mode: str | None = None,
    area: str = "VIEW_3D",
    select: Iterable[Any] | None = None,
) -> ResolvedContext:
    """Return a context manager that sets the given context and restores it on exit.

    ``active``/``select`` accept object names (str) or object datablocks. ``mode`` is
    one of OBJECT/EDIT/SCULPT/etc. (case-insensitive). ``area`` is the editor type used
    for ``temp_override`` (default VIEW_3D); skipped when no such area exists (headless).
    """
    return ResolvedContext(active=active, mode=mode, area=area, select=select)


def check_poll(op: Any, message: str | None = None, **override: Any) -> None:
    """Raise a clean ``precondition_failed`` if an operator's ``poll()`` is False.

    Use before invoking an operator so the agent gets a structured precondition error
    rather than a raw ``RuntimeError`` from deep inside ``bpy.ops``::

        ctx.check_poll(bpy.ops.mesh.subdivide)
    """
    import bpy  # lazy

    poll = getattr(op, "poll", None)
    try:
        if override:
            with bpy.context.temp_override(**override):
                ok = bool(poll()) if poll is not None else True
        else:
            ok = bool(poll()) if poll is not None else True
    except Exception as exc:  # noqa: BLE001 - normalize to a precondition error
        raise PreconditionError(
            message or f"operator preconditions not met: {exc}", {"error": str(exc)}
        ) from exc
    if not ok:
        raise PreconditionError(message or "operator preconditions not met")
