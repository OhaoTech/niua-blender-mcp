"""Deterministic objective-gate checker.

Evaluates hard thresholds against the nested metrics dict from feedback.quality.
Pure Python, no bpy, no network: fully unit-testable offline.
"""

from __future__ import annotations

import operator
from typing import Any

_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "<": operator.lt, ">": operator.gt}


def _dig(metrics: dict, path: str) -> Any:
    cur: Any = metrics
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def check_gates(metrics: dict, gates: list[dict]) -> dict:
    results = []
    all_pass = True
    for gate in gates:
        actual = _dig(metrics, gate["path"])
        fn = _OPS.get(gate["op"])
        ok = bool(actual is not None and fn is not None and fn(actual, gate["value"]))
        all_pass = all_pass and ok
        results.append(
            {
                "path": gate["path"],
                "op": gate["op"],
                "value": gate["value"],
                "actual": actual,
                "pass": ok,
            }
        )
    return {"gates": results, "gates_pass": all_pass}
