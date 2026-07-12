"""Bench 'turns' metric: finisher tool-call count per item, recorded in meta only
(items/reading -- the byte-identity surface -- stay untouched)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_objective_benchmark.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_objective_benchmark", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBridge:
    """Answers just enough of the tool surface for run_item's recipe path."""

    def __init__(self) -> None:
        self.objects: list[str] = []

    def call(self, command: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        payload = payload or {}
        if command == "scene.info":
            return {"objects": [{"name": n, "type": "MESH"} for n in self.objects]}
        if command == "scene.create_object":
            self.objects.append("Cube")
            return {"name": "Cube"}
        if command == "object.rename":
            self.objects[self.objects.index(payload["object"])] = payload["name"]
            return {"name": payload["name"]}
        if command == "object.delete":
            for name in payload["objects"].split(","):
                if name in self.objects:
                    self.objects.remove(name)
            return {"deleted": True}
        if command == "feedback.capture_intake":
            return {"available": True}
        if command == "feedback.readiness":
            return {"available": True, "readiness": 0.5, "stage_pass_fraction_mean": 0.5}
        if command == "feedback.preservation":
            return {"available": True, "preservation": 1.0}
        return {}


ITEM = {
    "id": "t1",
    "asset_class": "hard_surface_prop",
    "input": {"recipe": [{"tool": "scene.create_object", "args": {"type": "CUBE"}}]},
}


def test_finisher_turns_counts_tool_calls() -> None:
    module = _load_module()

    def three_call_finisher(bridge, subject, item):
        for _ in range(3):
            bridge.call("scene.info", {})

    turns: dict[str, int] = {}
    card = module.run_item(FakeBridge(), ITEM, three_call_finisher, None, turns=turns)
    assert turns == {"t1": 3}
    assert "finisher_turns" not in card  # never in the items section
    assert card["id"] == "t1"


def test_baseline_no_op_finisher_scores_zero_turns() -> None:
    module = _load_module()
    turns: dict[str, int] = {}
    module.run_item(FakeBridge(), ITEM, module._no_op_finisher, None, turns=turns)
    assert turns == {"t1": 0}
