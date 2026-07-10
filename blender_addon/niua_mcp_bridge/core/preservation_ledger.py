# blender_addon/niua_mcp_bridge/core/preservation_ledger.py
"""Thin passive per-object preservation ledger (NOT the pipeline FSM).

A plain per-object scratchpad the ruler reads/writes: intake silhouette masks + the intake
bbox + a generic session-checkpoint label. This ledger is a passive per-object scratchpad;
it holds no stage/order/progress state.
"""

from __future__ import annotations

from typing import Any

PRESERVATION_FLOOR = 0.85                       # locked global do-no-harm floor (per-class later)
PRESERVATION_VIEWS = ("front", "right", "top")  # ortho-only; persp excluded
PRESERVATION_RES = 256

_LEDGER: dict[str, dict[str, Any]] = {}


def reset() -> None:
    _LEDGER.clear()


def set_intake(object_name: str, record: dict[str, Any]) -> None:
    _LEDGER[object_name] = record


def get_intake(object_name: str) -> dict[str, Any] | None:
    return _LEDGER.get(object_name)
