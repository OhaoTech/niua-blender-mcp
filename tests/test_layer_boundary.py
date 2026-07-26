"""Import-direction guard: interface modules must never import from the finishing layer.

AST-based and fully offline (no bpy, no Blender). Two things are checked per side:

1. Every ``.py`` file OUTSIDE the declared policy area contains no import that
   references ``finishing`` or ``evals`` anywhere in the dotted path -- not even inside
   a function body (the addon's ``domains/eyes.py`` used to import
   ``finishing_feedback.quality`` lazily inside a handler before it was declared a
   policy domain; this test walks the whole AST, not just the module body, so a lazy
   import would be caught too).
2. The two ``finishing_feedback`` modules (addon + server) register exactly the six
   expected policy tool names, and the addon's ``domains/asset_class.py`` registers
   exactly its two current names -- so a future edit that quietly grows or shrinks the
   policy surface trips this test instead of drifting unnoticed.

Policy areas (the only places allowed to import finishing/evals) are declared here as
the single source of truth for the plan's "Known classification" list. If this test
ever fails against a clean split, the split missed an edge -- fix the split, not the
allowlist (see docs/superpowers/plans/2026-07-10-two-layer-split.md, Task C).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ADDON_ROOT = REPO_ROOT / "blender_addon" / "niua_mcp_bridge"
SERVER_ROOT = REPO_ROOT / "src" / "niua_blender_mcp"

#: Paths (relative to their root) that are allowed to import finishing/evals.
#: Directories end with "/" and match any file below them; bare names match one file.
ADDON_POLICY_AREA = {
    "finishing/",  # the whole finishing/ package
    "domains/policy/",  # every policy domain, now a real package the artifact omits
    # INTERFACE, with an optional policy garnish: wire_shaded/lookdev fold
    # feedback.quality analytics into their capture bundle when the policy layer happens
    # to be installed. The import is guarded (see eyes._policy_analytics) precisely so
    # these tools keep working in a pure-MCP install -- the render is the product, the
    # analytics are a bonus. Declared here because the edge is real, not because the
    # module needs policy to function.
    "domains/eyes.py",
}

SERVER_POLICY_AREA = {
    "finishing/",
    "evals/",
    "domains/policy/",
}

FORBIDDEN_TOKENS = {"finishing", "evals"}


def _in_policy_area(rel_path: Path, policy_area: set[str]) -> bool:
    rel_str = rel_path.as_posix()
    for entry in policy_area:
        if entry.endswith("/"):
            if rel_str.startswith(entry):
                return True
        elif rel_str == entry:
            return True
    return False


def _iter_py_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _referenced_dotted_names(tree: ast.AST) -> set[str]:
    """Every module path referenced by an import anywhere in the file (any depth)."""
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                refs.add(node.module)
            # Catches "from .. import finishing" / "from . import evals" style
            # imports, where the forbidden token is the imported name, not the module.
            for alias in node.names:
                refs.add(alias.name)
    return refs


def _mentions_forbidden(refs: set[str]) -> set[str]:
    hits: set[str] = set()
    for ref in refs:
        parts = ref.split(".")
        if FORBIDDEN_TOKENS & set(parts):
            hits.add(ref)
    return hits


#: Floor guard: each side currently has ~70 modules. If the walk ever visits fewer than
#: this, the roots went stale (rename/restructure) and the tripwire would be checking
#: nothing -- fail loud instead of silently passing.
_MIN_FILES_PER_SIDE = 40


def _check_side(root: Path, policy_area: set[str]) -> list[str]:
    violations: list[str] = []
    files = list(_iter_py_files(root))
    assert len(files) >= _MIN_FILES_PER_SIDE, (
        f"boundary walk visited only {len(files)} files under {root} -- stale root?"
    )
    for path in files:
        rel = path.relative_to(root)
        if _in_policy_area(rel, policy_area):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = _mentions_forbidden(_referenced_dotted_names(tree))
        if hits:
            violations.append(f"{rel.as_posix()}: {sorted(hits)}")
    return violations


def test_addon_interface_never_imports_finishing() -> None:
    violations = _check_side(ADDON_ROOT, ADDON_POLICY_AREA)
    assert not violations, "interface -> finishing import(s) found:\n" + "\n".join(violations)


def test_server_interface_never_imports_finishing_or_evals() -> None:
    violations = _check_side(SERVER_ROOT, SERVER_POLICY_AREA)
    assert not violations, "interface -> finishing/evals import(s) found:\n" + "\n".join(violations)


#: The six feedback/io policy tools that moved into finishing_feedback.py on both sides.
EXPECTED_FINISHING_FEEDBACK_NAMES = {
    "feedback.quality",
    "feedback.critique",
    "feedback.capture_intake",
    "feedback.preservation",
    "feedback.readiness",
    "io.profile_validate",
}

EXPECTED_ASSET_CLASS_NAMES = {
    "asset_class.list",
    "asset_class.describe",
}


def test_addon_finishing_feedback_registers_exactly_six_tools() -> None:
    from niua_mcp_bridge.domains.policy import finishing_feedback

    names = {command.name for command in finishing_feedback.COMMANDS}
    assert names == EXPECTED_FINISHING_FEEDBACK_NAMES


def test_server_finishing_feedback_registers_exactly_six_tools() -> None:
    from niua_blender_mcp.domains.policy import finishing_feedback

    names = {spec.name for spec in finishing_feedback.SPECS}
    assert names == EXPECTED_FINISHING_FEEDBACK_NAMES


def test_addon_asset_class_registers_exactly_its_current_names() -> None:
    from niua_mcp_bridge.domains.policy import asset_class

    names = {command.name for command in asset_class.COMMANDS}
    assert names == EXPECTED_ASSET_CLASS_NAMES


def test_client_sdk_is_interface_never_imports_finishing_or_evals() -> None:
    """The generated tool-client SDK is interface-layer: it must not import finishing/evals."""
    root = SERVER_ROOT / "client"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
            elif isinstance(node, ast.Import):
                mod = ",".join(a.name for a in node.names)
            if "finishing" in mod or "evals" in mod:
                offenders.append(f"{path.name}: {mod}")
    assert not offenders, offenders
