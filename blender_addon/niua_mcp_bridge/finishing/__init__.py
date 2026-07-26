"""The policy layer (add-on side): game-asset opinions built on the generic interface.

Everything here encodes game-asset policy -- budgets, gate thresholds, PBR/LOD/collision
conventions, engine/export profiles, asset-class defaults, do-no-harm preservation
bookkeeping. It is the "finishing" half of the two-layer split: the interface
(``..core``, ``..domains`` outside the declared policy modules) is neutral Blender
translation/measurement that could serve any Blender automation; this package is the
opinionated part.

The opinions are defaults, not couplings. Nothing here knows about any particular
generator, pipeline, or vendor: the numbers live in ``asset_classes.py`` as data and the
caller can override them per request. Swapping this package out leaves a working, neutral
Blender MCP behind -- that is the whole point of the split, and what keeps this tool
usable by anyone rather than by one studio.

Import-direction rule (enforced by ``tests/test_layer_boundary.py``):
finishing may import interface (``..core``, ``..domains.mesh``, etc.) -- that direction
is fine, policy code measuring itself with generic tools. The reverse is FORBIDDEN:
interface modules must never import from this package. The only ``domains/`` modules
allowed to import from ``finishing`` are the declared policy domains
(``domains/finishing_feedback.py``, ``domains/asset_class.py``).
"""

from __future__ import annotations
