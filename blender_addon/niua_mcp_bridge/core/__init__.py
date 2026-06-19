"""Kernel core for the add-on: stable plumbing handlers build on.

Currently the context resolver (``context.ResolvedContext`` + ``ensure``). Importable
without bpy at module top (bpy is imported lazily inside methods) so fake-bpy unit tests
work unchanged.
"""

from __future__ import annotations

from .context import PreconditionError, ResolvedContext, check_poll, ensure

__all__ = ["ResolvedContext", "ensure", "check_poll", "PreconditionError"]
