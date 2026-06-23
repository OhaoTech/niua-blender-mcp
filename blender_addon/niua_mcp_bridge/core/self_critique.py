"""Deterministic stage self-critique."""

from __future__ import annotations

from typing import Any


def critique_stage(
    stage: str,
    gate_result: dict[str, Any],
    pack: dict[str, Any],
    *,
    attempt: int = 1,
    max_attempts: int = 3,
) -> dict[str, Any]:
    failed = [gate for gate in gate_result.get("gates", []) if not gate.get("pass", False)]
    suggestions = pack.get("recommendations", {})
    recommendations = []
    for gate in failed:
        path = gate.get("path", "")
        recommendations.append(suggestions.get(path, f"Fix gate {path} before advancing."))
    return {
        "stage": stage,
        "attempt": int(attempt),
        "max_attempts": int(max_attempts),
        "gates_pass": bool(gate_result.get("gates_pass", False)),
        "failed_count": len(failed),
        "failed_gates": failed,
        "standards": pack.get("standards", ""),
        "targets": pack.get("targets", {}),
        "sources": pack.get("sources", []),
        "recommendations": recommendations,
        "may_retry": bool(failed) and int(attempt) < int(max_attempts),
    }
