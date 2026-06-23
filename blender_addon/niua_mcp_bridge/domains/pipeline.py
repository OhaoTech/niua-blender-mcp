"""Layer 2 pipeline command handlers."""

from __future__ import annotations

from ..context import Ctx
from ..core import pipeline as store
from ..core import session as session_store
from ..dispatch import Command
from ..errors import INVALID_PARAMS, PRECONDITION, BridgeError
from .feedback import quality
from .session import _resolve_object


def _object_name(payload: dict) -> str | None:
    name = payload.get("object")
    return name if isinstance(name, str) and name else None


def start(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    profile = payload.get("profile")
    profile = profile if isinstance(profile, str) and profile else "game_asset"
    label = "pipeline:intake:entry"
    session_store.checkpoint(obj, label=label)
    return store.start(obj.name, profile=profile)


def status(ctx: Ctx, payload: dict) -> dict:
    return store.status(_object_name(payload))


def _stage_for_gate_check(object_name: str, payload: dict) -> str:
    stage = payload.get("stage")
    if isinstance(stage, str) and stage:
        return stage
    state = store.get_state(object_name)
    if state is None:
        raise BridgeError(PRECONDITION, f"pipeline has not started for object: {object_name}")
    return str(state["current_stage"])


def gate_check(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    if store.get_state(obj.name) is None:
        raise BridgeError(PRECONDITION, f"pipeline has not started for object: {obj.name}")

    stage = _stage_for_gate_check(obj.name, payload)
    try:
        gates = store.stage_gates(stage)
    except ValueError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc

    metrics = quality(ctx, {"object": obj.name})
    checked = store.check_gates(metrics, gates)
    gate_record = {
        "stage": stage,
        "gate_profile": store.gate_profile(stage),
        **checked,
    }
    state = store.record_gate(obj.name, stage, gate_record)
    return {
        "object": obj.name,
        "stage": stage,
        "metrics": metrics,
        **checked,
        "state": state,
    }


COMMANDS = [
    Command("pipeline.start", start, mutates=False),
    Command("pipeline.status", status, mutates=False),
    Command("pipeline.gate_check", gate_check, mutates=False),
]
