"""Layer 2 pipeline command handlers."""

from __future__ import annotations

from ..context import Ctx
from ..core import knowledge
from ..core import pipeline as store
from ..core.self_critique import critique_stage
from ..core import session as session_store
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError
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

    metrics_payload = dict(payload)
    metrics_payload["object"] = obj.name
    metrics = quality(ctx, metrics_payload)
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


def advance(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    checked = gate_check(ctx, {"object": obj.name})
    if not checked["gates_pass"]:
        raise BridgeError(
            PRECONDITION,
            f"stage gates have not passed: {checked['stage']}",
            {"stage": checked["stage"], "gates": checked["gates"]},
        )

    try:
        state = store.advance(obj.name)
    except ValueError as exc:
        raise BridgeError(PRECONDITION, str(exc)) from exc

    to_stage = state["state"]["current_stage"]
    label = state["state"]["checkpoints"].get(to_stage)
    if label:
        session_store.checkpoint(obj, label=label)
    return {
        "object": obj.name,
        "from_stage": checked["stage"],
        "to_stage": to_stage,
        "gate": {"gates": checked["gates"], "gates_pass": checked["gates_pass"]},
        "state": state,
    }


def rollback(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    state = store.get_state(obj.name)
    if state is None:
        raise BridgeError(PRECONDITION, f"pipeline has not started for object: {obj.name}")

    stage = payload.get("stage")
    stage = stage if isinstance(stage, str) and stage else state["current_stage"]
    label = state["checkpoints"].get(stage)
    if not label:
        raise BridgeError(NOT_FOUND, f"no pipeline checkpoint for {obj.name} at stage {stage}")

    snapshot = session_store.get_snapshot(obj.name, label)
    if snapshot is None:
        raise BridgeError(NOT_FOUND, f"no checkpoint for {obj.name} with label {label}")

    session_store.restore(obj, snapshot)
    try:
        state_out = store.rollback_pointer(obj.name, stage)
    except ValueError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc
    return {"object": obj.name, "stage": stage, "label": label, "state": state_out}


def self_critique(ctx: Ctx, payload: dict) -> dict:
    obj = _resolve_object(ctx, payload)
    checked = gate_check(ctx, {"object": obj.name, "stage": payload.get("stage")})
    stage = checked["stage"]
    try:
        pack = knowledge.stage_pack(stage)
    except KeyError as exc:
        raise BridgeError(INVALID_PARAMS, str(exc)) from exc
    gate = {"gates": checked["gates"], "gates_pass": checked["gates_pass"]}
    critique = critique_stage(
        stage,
        gate,
        pack,
        attempt=int(payload.get("attempt", 1)),
        max_attempts=int(payload.get("max_attempts", 3)),
    )
    return {
        "object": obj.name,
        "stage": stage,
        "gate": gate,
        "critique": critique,
        "state": checked["state"],
    }


COMMANDS = [
    Command("pipeline.start", start, mutates=False),
    Command("pipeline.status", status, mutates=False),
    Command("pipeline.gate_check", gate_check, mutates=False),
    Command("pipeline.advance", advance, mutates=False),
    Command("pipeline.rollback", rollback, mutates=True),
    Command("pipeline.self_critique", self_critique, mutates=False),
]
