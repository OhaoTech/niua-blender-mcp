"""Auto-discovery registration: domains register with zero __init__.py edits.

Server domain modules expose ``SPECS``; add-on domain modules expose ``COMMANDS``.
``build_router`` / ``build_default_registry`` import every sibling module and aggregate.
"""

from __future__ import annotations

import importlib

import niua_blender_mcp.domains as server_domains
import niua_mcp_bridge.domains as addon_domains
from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.dispatch import Command
from niua_mcp_bridge.domains import build_default_registry
from niua_blender_mcp.kernel import ToolSpec


def test_server_autodiscovers_all_sibling_specs() -> None:
    commands = {spec.command for spec in build_router().specs()}
    assert {
        "scene.info",
        "scene.create_object",
        "scene.set_transform",
        "rna.describe",
        "feedback.capture",
        "system.execute_python",
    } <= commands


def test_addon_autodiscovers_all_sibling_commands() -> None:
    names = build_default_registry().names()
    assert {
        "scene.info",
        "scene.create_object",
        "scene.set_transform",
        "rna.describe",
        "feedback.capture",
        "system.execute_python",
    } <= names


def test_every_server_domain_module_exposes_specs() -> None:
    # The discovery convention itself: each non-package sibling module that defines
    # SPECS contributes only ToolSpec instances.
    import pkgutil

    found = 0
    for info in pkgutil.iter_modules(server_domains.__path__):
        if info.ispkg:
            continue
        mod = importlib.import_module(f"{server_domains.__name__}.{info.name}")
        specs = getattr(mod, "SPECS", None)
        if specs is not None:
            found += 1
            assert all(isinstance(s, ToolSpec) for s in specs)
    assert found >= 4


def test_every_addon_domain_module_exposes_commands() -> None:
    import pkgutil

    found = 0
    for info in pkgutil.iter_modules(addon_domains.__path__):
        if info.ispkg:
            continue
        mod = importlib.import_module(f"{addon_domains.__name__}.{info.name}")
        cmds = getattr(mod, "COMMANDS", None)
        if cmds is not None:
            found += 1
            assert all(isinstance(c, Command) for c in cmds)
    assert found >= 4


def test_curated_beats_rna_regardless_of_discovery_order() -> None:
    # Discovery order is arbitrary (pkgutil); a generated spec must never clobber a
    # curated one with the same name. Exercise the router contract directly.
    router = build_router()
    curated = ToolSpec(name="scene.info", category="scene", summary="curated", command="scene.info")
    rna = ToolSpec(
        name="scene.info", category="scene", summary="generated", command="scene.info", source="rna"
    )
    router.register(rna)  # generated arrives after curated discovery
    assert router.get("scene.info").source == "curated"
    router.register(curated)
    router.register(rna)
    assert router.get("scene.info").summary == "curated"
