"""Decoupling invariant: the vendor brand must not be stamped into the user's data.

This tool is meant to be usable by anyone, not just its author, and that promise is easy
to erode one string literal at a time. The line this test draws:

* **Product identity is fine.** The add-on is *called* "Niua MCP Bridge" -- its ``bl_info``
  name, its N-panel label, its operator ids (``niua.start_server``), its env vars
  (``NIUA_BLENDER_MCP_*``), its distribution name (``niua-blender-mcp``) and its module
  paths all legitimately carry the name. None of those touch a user's document.
* **The user's document is not.** Datablocks we inject into their scene, custom-property
  keys that ride along on their exported asset, files we write to their disk, and entries
  we push onto their undo stack are *their* data. Those get a functional ``mcp_`` prefix
  that says what the thing is, not who made it. A stranger opening the outliner after a
  finishing run should see ``__mcp_capture_cam``, not somebody's company name.

So the forbidden pattern is narrow and mechanical: the brand used as an *identifier* --
``niua_`` or ``niua:`` in a string literal. That is what a datablock, property key, or
undo label looks like. Prose, labels, and dotted/hyphenated identity names all pass.
"""

from __future__ import annotations

import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SHIPPED_ROOTS = (
    REPO_ROOT / "src" / "niua_blender_mcp",
    REPO_ROOT / "blender_addon" / "niua_mcp_bridge",
)

#: Brand used as an identifier: `niua_foo` (datablock/file/property name) or `niua:foo`
#: (custom-property key, undo label). Case-sensitive on purpose -- `NIUA_BLENDER_MCP_*`
#: env vars and the `Niua MCP` display name are identity, not user data.
_BRAND_AS_IDENTIFIER = re.compile(r"niua[_:]")

#: The only tolerated matches, each for a stated reason.
_ALLOWED = {
    # Python module paths. These name our own importable code, never the user's data.
    "niua_blender_mcp",
    "niua_mcp_bridge",
    # A registered `bpy.types.Scene` property. Blender add-ons conventionally namespace
    # their Scene props by add-on name, and this one gates `execute_python`, so renaming
    # it would silently reset a security toggle in every already-saved .blend. Deliberate
    # exception, not an oversight.
    "niua_allow_python",
}


def _string_constants(tree: ast.AST) -> list[tuple[int, str]]:
    """Every string literal in ``tree`` except docstrings (those are prose, not data)."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                found.append((node.lineno, node.value))
    return found


def _offending(text: str) -> bool:
    """True when ``text`` uses the brand as an identifier outside the allowed names."""
    scrubbed = text
    for allowed in _ALLOWED:
        scrubbed = scrubbed.replace(allowed, "")
    return bool(_BRAND_AS_IDENTIFIER.search(scrubbed))


def test_brand_is_never_used_as_an_identifier_in_user_data() -> None:
    offenders: dict[str, list[str]] = {}
    scanned = 0
    for root in SHIPPED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            scanned += 1
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            hits = [f"line {ln}: {val!r}" for ln, val in _string_constants(tree) if _offending(val)]
            if hits:
                offenders[str(path.relative_to(REPO_ROOT))] = hits

    assert scanned > 0, "no modules scanned -- the paths in this test are wrong"
    assert not offenders, (
        "the vendor brand is being stamped into user data (datablock name, property key, "
        "written file, or undo label). Use a functional 'mcp_' prefix instead, so the name "
        f"describes what the thing is rather than who made it. Offenders: {offenders}"
    )


def test_the_allowlist_still_describes_real_code() -> None:
    """A stale allowlist silently widens the rule; every entry must still be in use."""
    corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for root in SHIPPED_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    unused = sorted(name for name in _ALLOWED if name not in corpus)
    assert not unused, f"allowlist entries no longer present in the code; drop them: {unused}"
