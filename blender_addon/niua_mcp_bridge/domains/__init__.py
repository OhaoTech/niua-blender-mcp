"""Domain packs. Each module exposes COMMANDS; build_default_registry aggregates them."""

from __future__ import annotations

from ..dispatch import Registry
from . import feedback, introspection, scene, system


def build_default_registry() -> Registry:
    registry = Registry()
    registry.add(scene.COMMANDS)
    registry.add(system.COMMANDS)
    registry.add(introspection.COMMANDS)
    registry.add(feedback.COMMANDS)
    return registry
