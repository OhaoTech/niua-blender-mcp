"""N-panel UI for the visible-GUI workflow: Start/Stop the bridge and see status.

Imported lazily from register() so the package stays importable without bpy.

Two defaults here are deliberately "on", both for the same reason -- an agent driving
Blender should not depend on a human having clicked something first:

* **autostart** -- the bridge comes up with Blender. Requiring a trip to the N-panel
  before every session is the difference between an unattended run and a babysat one.
* **allow_python** -- ``execute_python`` is reachable, so an agent can get at the verb
  nobody wrapped yet. The preference stays so it can be turned *off*, and it lives in
  add-on preferences rather than on the Scene, so the answer belongs to this machine
  instead of travelling inside a shared .blend.

Both are overridable from the environment (``NIUA_BLENDER_MCP_AUTOSTART``,
``NIUA_BLENDER_MCP_PORT``) so CI and headless workers can pin them without touching
saved preferences.
"""

from __future__ import annotations

import os

import bpy

from . import bridge_server

DEFAULT_PORT = 8765

#: Blender's startup calls register() before the window manager is fully up, so the
#: socket + drain timer are armed from a one-shot timer instead of directly.
_AUTOSTART_DELAY_S = 0.25


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _env_port(default: int) -> int:
    raw = os.environ.get("NIUA_BLENDER_MCP_PORT")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class NIUA_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    autostart: bpy.props.BoolProperty(
        name="Start bridge with Blender",
        description=(
            "Open the localhost port as soon as Blender loads, so an agent can drive "
            "this session without anyone pressing Start first"
        ),
        default=True,
    )

    port: bpy.props.IntProperty(
        name="Port",
        description="localhost port the bridge listens on",
        default=DEFAULT_PORT,
        min=1024,
        max=65535,
    )

    allow_python: bpy.props.BoolProperty(
        name="Allow execute_python",
        description=(
            "Let the bridge run arbitrary Python inside Blender. On by default so "
            "agents can reach verbs the tool surface does not cover. Turn off to "
            "restrict the bridge to its typed tools"
        ),
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "autostart")
        col.prop(self, "port")
        col.prop(self, "allow_python")
        if self.allow_python:
            col.label(
                text="Anything that can reach the port can run Python here",
                icon="ERROR",
            )
        else:
            col.label(text="system.execute_python will be refused", icon="INFO")


def _prefs(context):
    addon = context.preferences.addons.get(__package__)
    return getattr(addon, "preferences", None) if addon is not None else None


def _configured_port() -> int:
    prefs = _prefs(bpy.context)
    return _env_port(int(getattr(prefs, "port", DEFAULT_PORT)) if prefs is not None else DEFAULT_PORT)


def _autostart_once():
    """One-shot timer body: bring the bridge up once Blender's event loop is running.

    Never raises -- a failed autostart (port already taken by another Blender, most
    likely) must not take the add-on's registration down with it.
    """
    try:
        if bridge_server.is_running():
            return None
        prefs = _prefs(bpy.context)
        if prefs is not None and not prefs.autostart:
            return None
        if not _env_flag("NIUA_BLENDER_MCP_AUTOSTART", True):
            return None
        port = _configured_port()
        bridge_server.start(port=port)
        print(f"[niua] Blender Finisher listening on 127.0.0.1:{port}", flush=True)
    except Exception as exc:  # noqa: BLE001 - autostart is best-effort by design
        print(f"[niua] autostart failed ({exc}); use the Niua N-panel to start manually", flush=True)
    return None  # one-shot: returning None unregisters the timer


@bpy.app.handlers.persistent
def _restart_after_load(_dummy=None) -> None:
    """Re-arm the bridge after a file load that tore it down.

    Loading a .blend normally leaves the socket alone, but ``read_homefile`` /
    factory-settings re-registers add-ons and drops it. Idempotent: ``_start_socket``
    returns early when a server is already bound.
    """
    _autostart_once()


class NIUA_OT_start_server(bpy.types.Operator):
    bl_idname = "niua.start_server"
    bl_label = "Start Finisher"
    bl_description = "Start the localhost server so Niua Blender Finisher can drive this Blender"

    def execute(self, context):
        # No allow_python argument: the bridge reads the preference per request, so
        # toggling it takes effect immediately instead of at the next Start.
        port = _configured_port()
        bridge_server.start(port=port)
        self.report({"INFO"}, f"Niua Blender Finisher listening on 127.0.0.1:{port}")
        return {"FINISHED"}


class NIUA_OT_stop_server(bpy.types.Operator):
    bl_idname = "niua.stop_server"
    bl_label = "Stop Finisher"
    bl_description = "Stop the Niua Blender Finisher localhost server"

    def execute(self, context):
        bridge_server.stop()
        self.report({"INFO"}, "Niua Blender Finisher stopped")
        return {"FINISHED"}


class NIUA_PT_panel(bpy.types.Panel):
    bl_label = "Niua Blender Finisher"
    bl_idname = "NIUA_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Niua"

    def draw(self, context):
        layout = self.layout
        running = bridge_server.is_running()
        status = f"running :{_configured_port()}" if running else "stopped"
        layout.label(text=f"Status: {status}", icon="PLAY" if running else "PAUSE")
        prefs = _prefs(context)
        if prefs is not None:
            layout.prop(prefs, "autostart")
            layout.prop(prefs, "allow_python", text="Allow execute_python")
        row = layout.row()
        row.operator("niua.start_server", icon="PLAY")
        row.operator("niua.stop_server", icon="PAUSE")


_CLASSES = (NIUA_AddonPreferences, NIUA_OT_start_server, NIUA_OT_stop_server, NIUA_PT_panel)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    # Headless drivers own their own loop (bridge_server.serve_blocking) and have no
    # event loop to run timers, so autostart is a GUI-only concern.
    if not bpy.app.background:
        bpy.app.timers.register(_autostart_once, first_interval=_AUTOSTART_DELAY_S)
        if _restart_after_load not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(_restart_after_load)


def unregister() -> None:
    if _restart_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_restart_after_load)
    if bpy.app.timers.is_registered(_autostart_once):
        bpy.app.timers.unregister(_autostart_once)
    bridge_server.stop()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
