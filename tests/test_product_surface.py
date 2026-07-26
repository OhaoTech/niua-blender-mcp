"""What ships is the pure MCP: Blender translation plus eyes, no opinions.

The released add-on and wheel deliberately omit the policy layer. Not because the code is
bad, but because the *judgments* are not good enough to stand behind yet -- ``object.retopo``
reaches its triangle budget on simple props and cannot take a dense character there without
destroying it. A tool that fails on the hard case makes the whole MCP look broken when the
Blender surface underneath is fine, so it waits in the repo until it earns the release.

Exclusion works by absence: ``domains/__init__.py`` discovers a domain by the presence of
its module, so an artifact without ``domains/policy/`` is one where those tools do not
exist. That only holds if the policy tools live *entirely* inside that directory, which is
the property these tests pin -- one policy tool registered from a shipped module would
survive the exclusion and ship half a pipeline.
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDON_DOMAINS = REPO_ROOT / "blender_addon" / "niua_mcp_bridge" / "domains"
SERVER_DOMAINS = REPO_ROOT / "src" / "niua_blender_mcp" / "domains"

#: The tools that must disappear when the policy layer is left out. Verified against a
#: real artifact: building the add-on zip and importing it yields 292 tools instead of
#: 304, and the difference is exactly this set.
POLICY_TOOLS = {
    # measurement folded together with budgets/gates into a verdict
    "feedback.quality",
    "feedback.readiness",
    "feedback.critique",
    "feedback.preservation",
    "feedback.capture_intake",
    # export-profile policy
    "io.profile_validate",
    # the budget profiles themselves
    "asset_class.list",
    "asset_class.describe",
    # multi-step recipes built on stock Blender ops
    "object.retopo",
    "object.lod_create",
    "object.collision_hulls_create",
    "object.collision_proxy_create",
}


def _registered_names(path: pathlib.Path, attribute: str) -> set[str]:
    """Tool names a domain module registers, read statically from its COMMANDS/SPECS."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == attribute for t in node.targets)):
            continue
        for element in getattr(node.value, "elts", []):
            # Command("object.retopo", ...) -- positional; ToolSpec(name="...") -- keyword
            for arg in getattr(element, "args", []):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    names.add(arg.value)
                    break
            for keyword in getattr(element, "keywords", []):
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    names.add(keyword.value.value)
    return names


def _by_module(root: pathlib.Path, attribute: str) -> dict[pathlib.Path, set[str]]:
    out: dict[pathlib.Path, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found = _registered_names(path, attribute)
        if found:
            out[path.relative_to(root)] = found
    return out


def test_no_shipped_module_registers_a_policy_tool() -> None:
    """The load-bearing property: deleting policy/ deletes exactly the policy tools."""
    leaks: dict[str, list[str]] = {}
    for root, attribute in ((ADDON_DOMAINS, "COMMANDS"), (SERVER_DOMAINS, "SPECS")):
        for relative, names in _by_module(root, attribute).items():
            if relative.parts[0] == "policy":
                continue
            trespassing = sorted(names & POLICY_TOOLS)
            if trespassing:
                leaks[f"{root.parent.name}/domains/{relative}"] = trespassing
    assert not leaks, (
        "a policy tool is registered from a module that ships, so excluding domains/policy/ "
        f"would leave it exposed with its implementation gone: {leaks}"
    )


def test_policy_package_registers_exactly_the_policy_tools() -> None:
    """The other direction: nothing extra hides in policy/, so the cut stays honest."""
    for root, attribute in ((ADDON_DOMAINS, "COMMANDS"), (SERVER_DOMAINS, "SPECS")):
        registered: set[str] = set()
        for relative, names in _by_module(root, attribute).items():
            if relative.parts[0] == "policy":
                registered |= names
        assert registered == POLICY_TOOLS, (
            f"{root.parent.name} policy package registers {sorted(registered)}, "
            f"expected {sorted(POLICY_TOOLS)}"
        )


def test_the_addon_packager_excludes_the_policy_layer() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_addon_zip  # noqa: PLC0415

    shipped = {p.as_posix() for p in build_addon_zip.product_files()}
    policy = sorted(p for p in shipped if p.startswith(("domains/policy/", "finishing/")))
    assert not policy, f"the add-on artifact still contains the policy layer: {policy}"
    # ...and the build is not simply empty
    assert "domains/objects.py" in shipped and "domains/eyes.py" in shipped, (
        "the packager dropped interface modules it should keep"
    )


def test_dev_build_still_contains_everything() -> None:
    """--include-policy must remain a real escape hatch for benchmark work."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import build_addon_zip  # noqa: PLC0415

    dev = {p.as_posix() for p in build_addon_zip.product_files(include_policy=True)}
    assert "domains/policy/finishing_recipes.py" in dev
    assert "finishing/gates.py" in dev
