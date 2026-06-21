"""Statusbar GUI-parity tool specs."""

from __future__ import annotations

from ..kernel import ToolSpec

SPECS = [
    ToolSpec(
        name="statusbar.report",
        category="statusbar",
        summary="Report Status Bar context and scene statistics",
        command="statusbar.report",
    ),
]
