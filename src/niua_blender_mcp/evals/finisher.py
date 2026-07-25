"""Deterministic gate-driven finisher — the benchmark's reference finishing agent.

The finishing LOOP lives in finishing/skills/bake_and_finish.py (bake-transfer +
dual do-no-harm axes, fail-closed). This module keeps the benchmark's stable
entrypoint: `finish(bridge, subject, item)` wraps the bridge in a ToolSession and
delegates to that skill, so the objective benchmark measures the product default.
`TOOLS_USED` is re-exported for the runner's startup registration guard.

Wired into scripts/run_objective_benchmark.py via
  --mode agent --finisher niua_blender_mcp.evals.finisher:finish
"""

from __future__ import annotations

from typing import Any

from ..client import ToolSession
from ..finishing.skills import DEFAULT_SKILL, get_default_skill
from ..finishing.skills.bake_and_finish import (
    PRESERVATION_FLOOR,
    SURFACE_FIDELITY_FLOOR,
    TOOLS_USED,
    run,
)

__all__ = [
    "finish",
    "TOOLS_USED",
    "PRESERVATION_FLOOR",
    "SURFACE_FIDELITY_FLOOR",
    "DEFAULT_SKILL",
]

# Must stay aligned with finishing.skills.DEFAULT_SKILL (bake_and_finish).
assert DEFAULT_SKILL == "bake_and_finish"
assert get_default_skill().run is run


def finish(bridge: Any, subject: str, item: dict) -> dict:
    """Runner entrypoint: finish `subject` in place; returns a per-move report."""
    params = {"asset_class": item.get("asset_class"), "id": item.get("id", subject)}
    return run(ToolSession(bridge), subject, params)
