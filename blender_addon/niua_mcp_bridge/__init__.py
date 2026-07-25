"""Niua MCP Bridge add-on.

The in-Blender half of the agentic Blender MCP. A background socket server enqueues
requests; a bpy.app.timers callback drains them on the main thread and dispatches to
domain handlers (see dispatch.py). The N-panel + socket server + timer are wired in a
later Phase 0 chunk; this module stays importable without bpy so the dispatch core can
be unit-tested with a fake bpy.
"""

# SPDX-License-Identifier: GPL-3.0-or-later
#
# This package runs INSIDE Blender and imports bpy, so it is a derivative work of
# Blender (GPL-2.0-or-later) and must itself be GPL. The MCP server in ../../src is a
# separate process that never imports bpy and is Apache-2.0. See LICENSING.md.
from __future__ import annotations

bl_info = {
    "name": "Niua MCP Bridge",
    "author": "FrankYin",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Niua",
    "description": "Agentic Blender bridge for the Niua Blender MCP server",
    "category": "System",
    "doc_url": "https://github.com/FrankYin/niua-blender-mcp",
    "license": "SPDX:GPL-3.0-or-later",
}

from .domains import build_default_registry  # noqa: E402

__all__ = ["build_default_registry", "bl_info"]


def register() -> None:  # pragma: no cover - exercised by the headless smoke test / live Blender
    from . import ui

    ui.register()


def unregister() -> None:  # pragma: no cover
    from . import ui

    ui.unregister()
