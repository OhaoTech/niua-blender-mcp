"""N-panel UI for the visible-GUI workflow: Start/Stop the bridge and see status.

Imported lazily from register() so the package stays importable without bpy.
"""

from __future__ import annotations

import bpy

from . import bridge_server

DEFAULT_PORT = 8765


class NIUA_OT_start_server(bpy.types.Operator):
    bl_idname = "niua.start_server"
    bl_label = "Start Niua MCP Bridge"
    bl_description = "Start the localhost bridge so the MCP server can drive this Blender"

    def execute(self, context):
        allow = bool(getattr(context.scene, "niua_allow_python", False))
        bridge_server.start(port=DEFAULT_PORT, allow_python=allow)
        self.report({"INFO"}, f"Niua MCP bridge listening on 127.0.0.1:{DEFAULT_PORT}")
        return {"FINISHED"}


class NIUA_OT_stop_server(bpy.types.Operator):
    bl_idname = "niua.stop_server"
    bl_label = "Stop Niua MCP Bridge"
    bl_description = "Stop the localhost bridge"

    def execute(self, context):
        bridge_server.stop()
        self.report({"INFO"}, "Niua MCP bridge stopped")
        return {"FINISHED"}


class NIUA_PT_panel(bpy.types.Panel):
    bl_label = "Niua MCP"
    bl_idname = "NIUA_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Niua"

    def draw(self, context):
        layout = self.layout
        running = bridge_server.is_running()
        layout.label(text=f"Status: {'running' if running else 'stopped'}", icon="PLAY" if running else "PAUSE")
        layout.prop(context.scene, "niua_allow_python", text="Allow execute_python")
        row = layout.row()
        row.operator("niua.start_server", icon="PLAY")
        row.operator("niua.stop_server", icon="PAUSE")


_CLASSES = (NIUA_OT_start_server, NIUA_OT_stop_server, NIUA_PT_panel)


def register() -> None:
    bpy.types.Scene.niua_allow_python = bpy.props.BoolProperty(
        name="Allow execute_python", default=False
    )
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    bridge_server.stop()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.niua_allow_python
