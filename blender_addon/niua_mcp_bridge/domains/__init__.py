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


def _discover_commands() -> list[Command]:
    commands: list[Command] = []
    for info in pkgutil.iter_modules(__path__):
        if info.ispkg:
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        domain = getattr(module, DOMAIN_ATTR, None)
        if domain:
            commands.extend(domain)
    return commands


def build_default_registry() -> Registry:
    registry = Registry()
    registry.add(_discover_commands())
    return registry
