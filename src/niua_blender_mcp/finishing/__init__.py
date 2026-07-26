"""Finishing layer: game-asset policy (the product).

**Start with** ``finishing/skills/bake_and_finish.py`` (default skill) and repo
``START_HERE.md``.

This package holds the opinions: budgets, gates, skills. They are overridable
defaults, not couplings -- nothing here knows about any particular generator or
vendor. The rest of the MCP server is neutral Blender remote control (frozen
library), and it still works with this package removed.

Import rule (``tests/test_layer_boundary.py``): finishing may import interface;
interface must never import finishing (except declared policy domains on the addon).
"""

from __future__ import annotations
