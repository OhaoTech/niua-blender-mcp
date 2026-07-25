"""Finishing layer: game-asset policy (the product).

**Start with** ``finishing/skills/bake_and_finish.py`` (default skill) and repo
``START_HERE.md``.

This package holds NIUA's opinions: budgets, gates, skills. The rest of the MCP
server is neutral Blender remote control (frozen library).

Import rule (``tests/test_layer_boundary.py``): finishing may import interface;
interface must never import finishing (except declared policy domains on the addon).
"""

from __future__ import annotations
