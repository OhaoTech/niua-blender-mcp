"""Layer 2 pipeline tool manifest."""

from __future__ import annotations

from ..kernel import Str, ToolSpec

SPECS = [
    ToolSpec(
        name="pipeline.start",
        category="pipeline",
        summary="Start a gated Layer 2 game-asset pipeline run for an object",
        command="pipeline.start",
        params={
            "object": Str(required=True, summary="Object to track through the pipeline"),
            "profile": Str(default="game_asset", summary="Pipeline profile"),
        },
    ),
    ToolSpec(
        name="pipeline.status",
        category="pipeline",
        summary="Read pipeline state for one object, or all active pipeline runs",
        command="pipeline.status",
        params={
            "object": Str(summary="Object to inspect; all runs if omitted"),
        },
    ),
    ToolSpec(
        name="pipeline.gate_check",
        category="pipeline",
        summary="Evaluate objective gates for the current or named pipeline stage",
        command="pipeline.gate_check",
        params={
            "object": Str(required=True, summary="Object whose pipeline gates should be checked"),
            "stage": Str(summary="Stage to check; defaults to the object's current stage"),
        },
    ),
    ToolSpec(
        name="pipeline.advance",
        category="pipeline",
        summary="Gate-check the current stage and advance to the next stage when gates pass",
        command="pipeline.advance",
        params={
            "object": Str(required=True, summary="Object whose pipeline should advance"),
        },
    ),
    ToolSpec(
        name="pipeline.rollback",
        category="pipeline",
        summary="Restore a stage entry checkpoint and move the pipeline pointer back",
        command="pipeline.rollback",
        params={
            "object": Str(required=True, summary="Object whose pipeline checkpoint should be restored"),
            "stage": Str(summary="Stage checkpoint to restore; defaults to current stage"),
        },
        mutates=True,
    ),
]
