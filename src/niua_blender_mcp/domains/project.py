"""Project editor GUI-parity tool specs."""

from __future__ import annotations

from ..kernel import ToolSpec

SPECS = [
    ToolSpec(
        name="project.report",
        category="project",
        summary="Report active or detected Blender project state and project editor areas",
        command="project.report",
    ),
    ToolSpec(
        name="project.files",
        category="project",
        summary="List files for the active or detected Blender project",
        command="project.files",
    ),
    ToolSpec(
        name="project.settings",
        category="project",
        summary="Report project preferences, active project fields, and project.toml data",
        command="project.settings",
    ),
]
