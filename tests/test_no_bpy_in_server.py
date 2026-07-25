"""Licensing invariant: the MCP server must never import ``bpy``.

This is not a style rule -- it is what keeps the two halves of this repo separately
licensable (see LICENSING.md):

* ``blender_addon/`` imports ``bpy``, runs inside Blender, and is therefore a derivative
  work of Blender (GPL-2.0-or-later) -> it ships GPL-3.0-or-later.
* ``src/niua_blender_mcp/`` is a standalone process that reaches Blender only over a
  localhost socket -> it ships Apache-2.0.

If ``bpy`` ever leaks into the server package, the server stops being a separate work and
the Apache-2.0 grant becomes indefensible. The check is AST-based and walks the WHOLE
tree (not just module-level statements), so a lazy ``import bpy`` inside a function body
is caught too.
"""

from __future__ import annotations

import ast
import pathlib

SERVER_ROOT = pathlib.Path(__file__).resolve().parent.parent / "src" / "niua_blender_mcp"


def _bpy_imports(tree: ast.AST) -> list[str]:
    """Every import in ``tree`` that pulls in bpy (or a bpy submodule)."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name == "bpy" or a.name.startswith("bpy.")]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "bpy" or module.startswith("bpy."):
                found.append(module)
    return found


def test_server_package_never_imports_bpy() -> None:
    offenders: dict[str, list[str]] = {}
    scanned = 0
    for path in sorted(SERVER_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        hits = _bpy_imports(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if hits:
            offenders[str(path.relative_to(SERVER_ROOT.parent.parent))] = hits

    assert scanned > 0, "no server modules scanned -- the path in this test is wrong"
    assert not offenders, (
        "bpy must never be imported by the MCP server -- this breaks the Apache-2.0/GPL "
        f"separation documented in LICENSING.md. Offenders: {offenders}"
    )


def test_server_declares_no_runtime_dependencies() -> None:
    """A dependency-free server is part of the 'separate program' argument.

    Only RUNTIME deps matter here: `[project.optional-dependencies]` (pytest, pillow)
    are test-only and never installed for users. Adding a runtime dependency is allowed,
    but it should be a deliberate decision -- this test exists so it cannot happen
    silently and unlicensed code cannot ride along into the Apache-2.0 distribution.
    """
    pyproject = (SERVER_ROOT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    runtime = pyproject.split("[project.optional-dependencies]", 1)[0]
    assert "dependencies = []" in runtime, (
        "the server's RUNTIME dependency list changed; confirm the new dependency's "
        "license is compatible with Apache-2.0 redistribution, then update this test"
    )


def test_both_license_files_are_present_and_distinct() -> None:
    repo = SERVER_ROOT.parent.parent
    server_license = (repo / "LICENSE").read_text(encoding="utf-8")
    addon_license = (repo / "blender_addon" / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in server_license and "Version 2.0" in server_license
    assert "GNU GENERAL PUBLIC LICENSE" in addon_license and "Version 3" in addon_license
    assert (repo / "LICENSING.md").exists(), "LICENSING.md explains the split; keep it shipped"
