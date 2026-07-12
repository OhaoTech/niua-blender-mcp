"""Deterministic gate-driven finisher — the benchmark's reference finishing agent.

The finishing LOOP now lives in finishing/skills/make_game_ready.py (driven through the
code-mode SDK). This module keeps the benchmark's stable entrypoint: `finish(bridge,
subject, item)` wraps the bridge in a ToolSession and delegates to that skill, so the
objective benchmark measures the exact same behavior. `TOOLS_USED` is re-exported for
the runner's startup registration guard.

Wired into scripts/run_objective_benchmark.py via
  --mode agent --finisher niua_blender_mcp.evals.finisher:finish
"""

from __future__ import annotations

from typing import Any

from ..client import ToolSession
from ..finishing.skills.make_game_ready import PRESERVATION_FLOOR, TOOLS_USED, run

__all__ = ["finish", "TOOLS_USED", "PRESERVATION_FLOOR"]


def finish(bridge: Any, subject: str, item: dict) -> dict:
    """Runner entrypoint: finish `subject` in place; returns a per-move report."""
    params = {"asset_class": item.get("asset_class"), "id": item.get("id", subject)}
    return run(ToolSession(bridge), subject, params)
