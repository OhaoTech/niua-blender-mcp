"""Script space GUI-parity tool specs."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="script.report",
        category="script",
        summary="Report script-space operators, preferences, paths, and editor areas",
        command="script.report",
    ),
    ToolSpec(
        name="script.paths",
        category="script",
        summary="List Blender script search paths and configured script directories",
        command="script.paths",
    ),
    ToolSpec(
        name="script.run_file",
        category="script",
        summary="Run a Python file through Blender's script operator when Python execution is trusted",
        command="script.run_file",
        params={"path": Str(required=True, summary="Python file path")},
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="script.reload",
        category="script",
        summary="Reload Blender scripts when Python execution is trusted",
        command="script.reload",
        mutates=True,
        feedback="viewport",
    ),
]
