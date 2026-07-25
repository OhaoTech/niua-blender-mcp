"""Regression tests for the Blender 5.x API drift found by live dogfooding (0.1 release).

The offline suite validates schemas and server/add-on parity, but it cannot see the live
``bpy`` surface -- which is exactly where these three bugs lived. Each test below fails
against the pre-fix code and pins the behaviour we now depend on:

1. ``Ctx.get_object`` must reject a non-string name with a teachable INVALID_PARAMS
   instead of letting ``bpy_prop_collection.get(None)`` fail at the C level.
2. ``ui.screenshot`` must pick the right operator across the 5.x screenshot split and
   must never pass the removed ``full`` property.
3. Capture must restore the render engine BEFORE the viewport shading type, because
   ``space.shading.type`` is a dynamic enum that loses MATERIAL under Workbench.
"""

from __future__ import annotations

import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.core.capture import _restore_engine_then_shading
from niua_mcp_bridge.domains import ui as ui_domain
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


# --------------------------------------------------------------------------------------
# 1. get_object must not hand None to bpy
# --------------------------------------------------------------------------------------
class _ExplodingObjects:
    """Mimics bpy_prop_collection.get(), which raises at the C level on a non-string key."""

    def get(self, name):  # noqa: ANN001
        if not isinstance(name, str):
            raise SystemError(
                "<built-in method get of bpy_prop_collection object> "
                "returned a result with an exception set"
            )
        return None


@pytest.mark.parametrize("bad_name", [None, "", 0, [], {}])
def test_get_object_rejects_non_string_names_cleanly(bad_name) -> None:  # noqa: ANN001
    bpy = types.SimpleNamespace(data=types.SimpleNamespace(objects=_ExplodingObjects()))
    ctx = Ctx(bpy)
    with pytest.raises(BridgeError) as excinfo:
        ctx.get_object(bad_name)
    assert excinfo.value.code == INVALID_PARAMS
    # the message must teach, not leak the C-level text
    assert "non-empty string" in str(excinfo.value)
    assert "exception set" not in str(excinfo.value)


# --------------------------------------------------------------------------------------
# 2. ui.screenshot across the Blender 5.x operator split
# --------------------------------------------------------------------------------------
class _FakeOp:
    def __init__(self, recorder: list, idname: str) -> None:
        self._recorder = recorder
        self._idname = idname

    def __call__(self, **kwargs):  # noqa: ANN003
        self._recorder.append((self._idname, kwargs))

    def poll(self):  # noqa: ANN201
        return True


def _screenshot_ctx(recorder: list, *, operators: set[str], with_area: bool = False):
    """Fake bpy exposing only ``operators``.

    ``with_area`` adds a window/area/region so _resolve_target can build a real
    temp_override (the thing that stops screenshot_area writing a 1x1 pixel file).
    """

    class _Screen:
        def __init__(self) -> None:
            for name in ("screenshot", "screenshot_area"):
                if f"screen.{name}" in operators:
                    setattr(self, name, _FakeOp(recorder, f"screen.{name}"))

    if with_area:
        region = types.SimpleNamespace(type="WINDOW")
        area = types.SimpleNamespace(type="VIEW_3D", regions=[region], spaces=[])
        screen = types.SimpleNamespace(name="Layout", areas=[area])
        window = types.SimpleNamespace(screen=screen)
        wm = types.SimpleNamespace(windows=[window])
    else:
        wm = types.SimpleNamespace(windows=[])

    bpy = types.SimpleNamespace(
        ops=types.SimpleNamespace(screen=_Screen()),
        context=types.SimpleNamespace(window_manager=wm),
    )
    return Ctx(bpy)


def test_screenshot_uses_area_operator_for_editor_capture_on_blender5() -> None:
    """full=False on a 5.x build routes to screen.screenshot_area, never passing `full`."""
    calls: list = []
    ctx = _screenshot_ctx(
        calls,
        operators={"screen.screenshot", "screen.screenshot_area"},
        with_area=True,
    )
    result = ui_domain.screenshot(ctx, {"path": "/tmp/shot.png"})
    assert result["applied"] == ["screen.screenshot_area"]
    idname, kwargs = calls[0]
    assert idname == "screen.screenshot_area"
    assert "full" not in kwargs, "Blender 5.x removed `full`; passing it is a hard error"


def test_screenshot_window_capture_omits_removed_full_property() -> None:
    """full=True on a 5.x build uses screen.screenshot and still must not pass `full`."""
    calls: list = []
    ctx = _screenshot_ctx(
        calls, operators={"screen.screenshot", "screen.screenshot_area"}, with_area=True
    )
    ui_domain.screenshot(ctx, {"path": "/tmp/shot.png", "full": True})
    idname, kwargs = calls[0]
    assert idname == "screen.screenshot"
    assert "full" not in kwargs


def test_screenshot_still_passes_full_on_older_builds() -> None:
    """Pre-5.x had ONE operator that takes `full`; keep using it there."""
    calls: list = []
    ctx = _screenshot_ctx(calls, operators={"screen.screenshot"})
    ui_domain.screenshot(ctx, {"path": "/tmp/shot.png", "full": True})
    idname, kwargs = calls[0]
    assert idname == "screen.screenshot"
    assert kwargs["full"] is True


def test_screenshot_falls_back_to_window_when_no_editor_area() -> None:
    """No resolvable area => window grab + an explicit note, never a silent 1x1 file."""
    calls: list = []
    ctx = _screenshot_ctx(
        calls,
        operators={"screen.screenshot", "screen.screenshot_area"},
        with_area=False,
    )
    result = ui_domain.screenshot(ctx, {"path": "/tmp/shot.png"})
    assert result["applied"] == ["screen.screenshot"]
    assert "note" in result and "whole window" in result["note"]


# --------------------------------------------------------------------------------------
# 3. capture restore order (engine before shading)
# --------------------------------------------------------------------------------------
class _DynamicShading:
    """``space.shading`` whose enum depends on the engine, like real Blender."""

    def __init__(self, render) -> None:  # noqa: ANN001
        self._render = render
        self._type = "SOLID"

    @property
    def type(self):  # noqa: ANN201
        return self._type

    @type.setter
    def type(self, value):  # noqa: ANN001
        legal = ("WIREFRAME", "SOLID", "RENDERED")
        if self._render.engine == "BLENDER_WORKBENCH" and value not in legal:
            raise TypeError(f'bpy_struct: item.attr = val: enum "{value}" not found in {legal}')
        self._type = value


def test_restore_puts_engine_back_before_shading_type() -> None:
    """The exact live failure: viewport in MATERIAL + a SOLID capture (Workbench)."""
    render = types.SimpleNamespace(engine="BLENDER_WORKBENCH")
    shading = _DynamicShading(render)
    _restore_engine_then_shading(render, "BLENDER_EEVEE_NEXT", shading, "MATERIAL")
    assert render.engine == "BLENDER_EEVEE_NEXT"
    assert shading.type == "MATERIAL", "Material Preview must survive a capture"


def test_restore_is_best_effort_and_never_raises() -> None:
    """A restore failure must never become the caller's error."""

    class _Hostile:
        @property
        def type(self):  # noqa: ANN201
            return "SOLID"

        @type.setter
        def type(self, value):  # noqa: ANN001
            raise RuntimeError("boom")

    render = types.SimpleNamespace(engine="BLENDER_WORKBENCH")
    _restore_engine_then_shading(render, "BLENDER_EEVEE_NEXT", _Hostile(), "MATERIAL")
    assert render.engine == "BLENDER_EEVEE_NEXT"
