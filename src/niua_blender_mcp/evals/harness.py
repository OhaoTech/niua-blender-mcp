"""End-to-end task harness: produce -> observe -> gate -> judge -> scorecard.

Dependency-injected callables keep this module pure Python and testable offline.
Phase B can supply bridge-backed produce/observe functions and a real judge.
"""

from __future__ import annotations

from typing import Callable

from .gates import check_gates
from .judge import stub_judge


def run_task(
    task: dict,
    *,
    produce: Callable[[], object],
    observe: Callable[[], dict],
    judge: Callable[[list, list, str], dict] = stub_judge,
) -> dict:
    produce()
    obs = observe()
    gate = check_gates(obs.get("metrics", {}), task.get("gates", []))
    if gate["gates_pass"]:
        verdict = judge(obs.get("images", []), obs.get("overlays", []), task.get("rubric", ""))
    else:
        verdict = {"score": 0.0, "critique": "objective gates failed"}
    judge_score = float(verdict["score"])
    judge_pass = judge_score >= float(task.get("judge_threshold", 7.0))
    return {
        "task": task.get("id"),
        "gates": gate["gates"],
        "gates_pass": gate["gates_pass"],
        "judge_score": judge_score,
        "judge_critique": verdict.get("critique", ""),
        "judge_pass": judge_pass,
        "pass": gate["gates_pass"] and judge_pass,
    }
