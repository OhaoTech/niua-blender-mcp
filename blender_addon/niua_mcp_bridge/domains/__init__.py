"""Domain packs (add-on side).

Auto-discovery: every sibling module in this package that exposes a module-level
``COMMANDS: list[Command]`` is a domain. ``build_default_registry`` imports them all
and aggregates their commands. Adding a domain is dropping a new ``<name>.py`` here
that defines ``COMMANDS`` -- no edit to this file is required.

The mirror convention on the server side is a ``SPECS: list[ToolSpec]`` attribute; a
parity test enforces that the two command sets stay identical.
"""

from __future__ import annotations

import importlib
import pkgutil

from ..dispatch import Command, Registry

#: The module-level attribute each domain module must expose.
DOMAIN_ATTR = "COMMANDS"


def _iter_domain_modules(package: str, search_path: list[str]):
    """Every module under ``package``, descending into subpackages.

    Subpackages are how an optional group of domains is made *removable*: ``policy/``
    holds the opinionated tools and is not copied into the released add-on, so those
    tools cease to exist rather than existing-but-disabled. Discovery therefore has to
    walk into subpackages that are present, and must not care that one is missing.
    """
    for info in pkgutil.iter_modules(search_path):
        qualified = f"{package}.{info.name}"
        module = importlib.import_module(qualified)
        if info.ispkg:
            yield from _iter_domain_modules(qualified, list(module.__path__))
        else:
            yield module


def _discover_commands() -> list[Command]:
    commands: list[Command] = []
    for module in _iter_domain_modules(__name__, list(__path__)):
        domain = getattr(module, DOMAIN_ATTR, None)
        if domain:
            commands.extend(domain)
    return commands


def build_default_registry() -> Registry:
    registry = Registry()
    registry.add(_discover_commands())
    return registry
