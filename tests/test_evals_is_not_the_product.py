"""``evals/`` is the benchmark harness, not the MCP — and it has to stay that way.

The harness lives *inside* the server package (``src/niua_blender_mcp/evals/``) purely for
import convenience, which makes it the easiest boundary in the repo to erode by accident.
Two properties keep the arrangement honest, and both are cheap to break silently:

1. **It is a leaf.** The harness measures the product; the product must never reach back.
   A server module importing a benchmark rubric or the reference finisher would make the
   ruler part of the thing it measures -- the scores stop meaning anything, and shipping
   the server would start requiring the harness.
2. **It is not shipped.** Its fixtures are ~72 MB of real generator output that are
   deliberately untracked, so a wheel containing the harness contains a harness that can
   only fail: ``list_items()`` returns ``[]`` and ``load_item()`` raises ``KeyError``.

See ARCHITECTURE.md, "What is and isn't the MCP".
"""

from __future__ import annotations

import ast
import pathlib
import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER_ROOT = REPO_ROOT / "src" / "niua_blender_mcp"
ADDON_ROOT = REPO_ROOT / "blender_addon" / "niua_mcp_bridge"
EVALS_ROOT = SERVER_ROOT / "evals"


def _product_modules() -> list[pathlib.Path]:
    """Every shipped module: the server minus the harness, plus the whole add-on."""
    out: list[pathlib.Path] = []
    for root in (SERVER_ROOT, ADDON_ROOT):
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or EVALS_ROOT in path.parents:
                continue
            out.append(path)
    return out


def _imports_evals(tree: ast.AST) -> list[str]:
    """Every import in ``tree`` that reaches the harness, absolute or relative."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [
                a.name for a in node.names
                if a.name == "niua_blender_mcp.evals" or a.name.startswith("niua_blender_mcp.evals.")
            ]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # absolute: `from niua_blender_mcp.evals import x`
            if module == "niua_blender_mcp.evals" or module.startswith("niua_blender_mcp.evals."):
                found.append(module)
            # relative: `from .evals import x` / `from ..evals.benchmark import y`
            elif node.level and (module == "evals" or module.startswith("evals.")):
                found.append("." * node.level + module)
            # relative: `from . import evals`
            elif node.level and not module:
                found += [f"{'.' * node.level} import {a.name}" for a in node.names if a.name == "evals"]
    return found


def test_no_product_module_imports_the_harness() -> None:
    offenders: dict[str, list[str]] = {}
    modules = _product_modules()
    for path in modules:
        hits = _imports_evals(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if hits:
            offenders[str(path.relative_to(REPO_ROOT))] = hits

    assert modules, "no product modules scanned -- the paths in this test are wrong"
    assert EVALS_ROOT.is_dir(), "the harness moved; update this test"
    assert not offenders, (
        "the MCP must never import its own benchmark harness -- that makes the ruler part "
        f"of the thing it measures. Offenders: {offenders}"
    )


def test_the_harness_is_excluded_from_the_wheel() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    find = config["tool"]["setuptools"]["packages"]["find"]
    excluded = set(find.get("exclude", []))
    missing = {"niua_blender_mcp.evals", "niua_blender_mcp.evals.*"} - excluded
    assert not missing, (
        "the benchmark harness would ship in the wheel without its (untracked) fixtures, "
        f"so it could only ever fail to load an item. Missing exclude patterns: {missing}"
    )


def test_package_data_patterns_actually_match_files() -> None:
    """A stale package-data key is a silent no-op that hides what actually ships.

    Checking that the directory *exists* is not enough -- a leftover ``__pycache__`` keeps
    an otherwise-empty package looking alive, which is exactly how a dead
    ``niua_blender_mcp.playbooks`` entry survived until CI ran it on a clean checkout.
    So assert the declared globs match real files.
    """
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = config["tool"]["setuptools"].get("package-data", {})
    assert package_data, "no package-data declared; if that is deliberate, drop this test"

    stale: dict[str, str] = {}
    for dotted, patterns in package_data.items():
        directory = SERVER_ROOT / pathlib.Path(*dotted.split(".")[1:])
        if not directory.is_dir():
            stale[dotted] = "directory does not exist"
            continue
        if not any(match.is_file() for pattern in patterns for match in directory.glob(pattern)):
            stale[dotted] = f"no file matches {patterns}"
    assert not stale, f"package-data entries that ship nothing: {stale}"
