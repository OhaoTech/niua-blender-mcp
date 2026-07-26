"""Domain packs (server side): the ToolSpec manifests exposed to the agent.

Auto-discovery: every sibling module in this package that exposes a module-level
``SPECS: list[ToolSpec]`` is a domain. ``build_router`` imports them all and registers
their specs. Adding a domain is dropping a new ``<name>.py`` here that defines ``SPECS``
-- no edit to this file is required.

Command names must mirror the add-on's command registry, whose mirror convention is a
``COMMANDS: list[Command]`` attribute (a parity test guards this). The server validates
arguments against these specs before dispatching over the bridge. The router keeps
curated-over-rna precedence on name collisions, independent of discovery order.
"""

from __future__ import annotations

import importlib
import pkgutil

from ..codegen import generate_specs
from ..kernel import Router, ToolSpec

#: The module-level attribute each domain module must expose.
DOMAIN_ATTR = "SPECS"


def _iter_domain_modules(package: str, search_path: list[str]):
    """Every module under ``package``, descending into subpackages.

    Mirrors the add-on's discovery. Subpackages are how an optional group of domains is
    made *removable*: ``policy/`` is excluded from the wheel, so its tools cease to exist
    rather than existing-but-disabled. Discovery walks into subpackages that are present
    and must not care that one is missing.
    """
    for info in pkgutil.iter_modules(search_path):
        qualified = f"{package}.{info.name}"
        module = importlib.import_module(qualified)
        if info.ispkg:
            yield from _iter_domain_modules(qualified, list(module.__path__))
        else:
            yield module


def _discover_specs() -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for module in _iter_domain_modules(__name__, list(__path__)):
        domain = getattr(module, DOMAIN_ATTR, None)
        if domain:
            specs.extend(domain)
    return specs


def build_router() -> Router:
    router = Router()
    router.add(_discover_specs())  # curated-over-rna precedence lives in Router.register
    router.add(generate_specs())
    return router
