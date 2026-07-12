# tests/evals/test_primary_grade.py
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def test_objective_runner_is_the_primary_grade() -> None:
    from niua_blender_mcp.evals.objective_bench import aggregate_objective, score_item_objective  # noqa: F401
    assert (_REPO / "scripts" / "run_objective_benchmark.py").is_file()


def test_altimeter_marked_non_primary() -> None:
    text = (_REPO / "workflows" / "altimeter.mjs").read_text(encoding="utf-8")
    assert "NON-PRIMARY" in text
    assert "run_objective_benchmark" in text
