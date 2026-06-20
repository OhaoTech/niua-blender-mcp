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


def _discover_specs() -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for info in pkgutil.iter_modules(__path__):
        if info.ispkg:
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        domain = getattr(module, DOMAIN_ATTR, None)
        if domain:
            specs.extend(domain)
    return specs


def build_router() -> Router:
    router = Router()
    router.add(_discover_specs())  # curated-over-rna precedence lives in Router.register
    router.add(generate_specs())
    return router
