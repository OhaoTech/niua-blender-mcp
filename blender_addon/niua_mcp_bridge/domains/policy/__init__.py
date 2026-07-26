"""Policy domains: the opinionated tools, kept in a package so they can be left out.

Everything here answers "is this a *shippable game asset*?" rather than "how do I drive
Blender?". That is a judgment call about someone else's project, and the judgments we
encode are not good enough to ship yet -- the reducer still cannot take a dense character
to budget without destroying it -- so the released add-on does not include this directory.

Why a subpackage rather than a naming convention: ``domains/__init__.py`` discovers a
domain by the *presence of its module*, so deleting this directory deletes the tools. No
flag to forget, no dead code path to keep working, and the packaging config can exclude a
package but not individual modules. Absence is the guarantee.

What is here:

* ``finishing_feedback.py`` -- ``feedback.quality`` / ``readiness`` / ``critique`` /
  ``preservation`` / ``capture_intake``: measurement folded together with budgets, gates
  and asset-class thresholds into a verdict.
* ``asset_class.py`` -- ``asset_class.list`` / ``describe``: the budget profiles themselves.
* ``finishing_recipes.py`` -- ``object.retopo`` / ``lod_create`` / ``collision_*``:
  multi-step recipes built on stock Blender ops. Stock Blender is still there without
  them; ``modifiers.add`` with a DECIMATE modifier does what it always did.

The neutral half of the same measurements stays shipped: ``feedback.capture``,
``silhouette``, ``topology``, ``uv``, ``wire_shaded``, ``turntable`` and friends look at
the mesh and report what they see without deciding whether it is good enough.

See ARCHITECTURE.md, "What is and isn't the MCP".
"""

from __future__ import annotations
