"""App/session/file lifecycle tool specs."""

from __future__ import annotations

from ..kernel import Bool, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="app.info",
        category="app",
        summary="Report Blender runtime, active file, dirty state, scene, workspace, and render engine",
        command="app.info",
    ),
    ToolSpec(
        name="app.file_new",
        category="app",
        summary="Start a new empty file; force is required if current file is dirty",
        command="app.file_new",
        params={"force": Bool(default=False, summary="Discard unsaved changes")},
    ),
    ToolSpec(
        name="app.file_open",
        category="app",
        summary="Open an existing .blend file by absolute path; force is required if current file is dirty",
        command="app.file_open",
        params={
            "path": Str(required=True, summary="Absolute path to .blend file"),
            "force": Bool(default=False, summary="Discard unsaved changes"),
        },
    ),
    ToolSpec(
        name="app.file_save",
        category="app",
        summary="Save the current file, or save to an absolute path if the file is unsaved",
        command="app.file_save",
        params={"path": Str(summary="Absolute path used when saving an unsaved file")},
    ),
    ToolSpec(
        name="app.file_save_as",
        category="app",
        summary="Save the current file to a new absolute path and make it active",
        command="app.file_save_as",
        params={"path": Str(required=True, summary="Absolute output .blend path")},
    ),
    ToolSpec(
        name="app.file_save_copy",
        category="app",
        summary="Save a copy of the current file without changing the active file path",
        command="app.file_save_copy",
        params={"path": Str(required=True, summary="Absolute output .blend path")},
    ),
    ToolSpec(
        name="app.file_revert",
        category="app",
        summary="Reload the current file from disk; force is always required",
        command="app.file_revert",
        params={"force": Bool(default=False, summary="Confirm reload from disk")},
    ),
]
