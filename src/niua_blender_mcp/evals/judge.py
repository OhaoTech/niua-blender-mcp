"""Quality judge contract plus deterministic stub.

The real judge is a Phase-B multimodal agent, run as an adversarial multi-lens
panel. It is given multi-angle renders, eye overlays, and the task rubric, then
returns {"score": float 0-10, "critique": str}. It is not implemented here:
deterministic code cannot judge taste. Phase A ships only this contract and a
stub so the harness is unit-testable offline.

Judge signature:
    judge(images: list, overlays: list, rubric: str) -> {"score": float, "critique": str}
"""

from __future__ import annotations


def stub_judge(images: list, overlays: list, rubric: str, *, score: float = 8.0, critique: str = "stub") -> dict:
    return {"score": float(score), "critique": critique}
