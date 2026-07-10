"""The finisher's accept/revert loop, offline: a behavior-driven FakeBridge.

The FakeBridge holds a readiness STATE. Applying a tool named in `effects` transitions
the state; `session.revert` restores the pre-finish state (that is what revert means).
Tests assert behavior — state transitions and revert restoring state — never call-count
choreography.
"""

from __future__ import annotations

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.domains import build_router
from niua_blender_mcp.evals import finisher


def _readiness(score, failing=()):
    per_gate = [{"path": p, "op": "==", "value": True, "actual": False, "pass": False}
                for p in failing]
    per_gate.append({"path": "always.pass", "op": "==", "value": True, "actual": True, "pass": True})
    return {"readiness": score, "per_gate": per_gate}


class FakeBridge:
    """Behavior-driven bridge: readiness is a state; tools in `effects` transition it,
    session.revert restores the initial state."""

    def __init__(self, before, effects=None, preservation=1.0, fail_tools=()):
        self.before = before
        self.state = before
        self.effects = dict(effects or {})
        self.preservation = preservation
        self.fail_tools = set(fail_tools)
        self.calls = []

    def call(self, tool, payload):
        self.calls.append((tool, payload))
        if tool in self.fail_tools:
            raise BridgeError("internal_error", f"{tool} exploded")
        if tool in self.effects:
            self.state = self.effects[tool]
        if tool == "session.revert":
            self.state = self.before
        if tool == "feedback.readiness":
            return self.state
        if tool == "feedback.preservation":
            return {"available": True, "preservation": self.preservation}
        if tool == "feedback.quality":
            return {"topology": {"tris": 100000},
                    "asset_class": {"effective_defaults": {"triangle_budget": 5000}}}
        if tool == "scene.info":
            return {"objects": [{"name": "subject", "type": "MESH"}]}
        return {}

    def tools(self, *names):
        return [c for c in self.calls if c[0] in names]


ITEM = {"id": "t", "asset_class": "hard_surface_prop"}


def test_move_skipped_when_its_gates_pass():
    bridge = FakeBridge(_readiness(1.0))
    out = finisher.finish(bridge, "subject", ITEM)
    assert out["moves"] == []
    assert bridge.tools("session.checkpoint") == []
    assert bridge.state == _readiness(1.0)  # untouched


def test_improving_move_is_kept():
    # uv gates failing; applying the unwrap transitions readiness 0.5 -> 0.7
    improved = _readiness(0.7)
    bridge = FakeBridge(_readiness(0.5, ["uv.has_uvs"]),
                        effects={"uv.smart_unwrap": improved})
    out = finisher.finish(bridge, "subject", ITEM)
    kept = [m for m in out["moves"] if m["move"] == "uv_unwrap"]
    assert kept and kept[0]["kept"] is True
    assert bridge.tools("session.revert") == []
    assert bridge.tools("uv.smart_unwrap") and bridge.tools("uv.pack_islands")
    assert bridge.state == improved  # the improvement was kept
    assert out["readiness_final"] == 0.7


def test_regressing_move_is_reverted():
    # the unwrap makes things worse (0.5 -> 0.3, gate still failing) -> revert
    before = _readiness(0.5, ["uv.has_uvs"])
    bridge = FakeBridge(before,
                        effects={"uv.smart_unwrap": _readiness(0.3, ["uv.has_uvs"])})
    out = finisher.finish(bridge, "subject", ITEM)
    move = next(m for m in out["moves"] if m["move"] == "uv_unwrap")
    assert move["kept"] is False
    reverts = bridge.tools("session.revert")
    assert reverts and reverts[0][1]["label"] == "finisher:uv_unwrap"
    assert bridge.state == before  # revert restored the pre-move state
    assert out["readiness_final"] == 0.5


def test_harm_below_preservation_floor_reverts_even_if_readiness_rose():
    # decimate raises readiness 0.5 -> 0.9 but preservation is 0.5 < 0.85 -> revert
    before = _readiness(0.5, ["engine.within_triangle_budget"])
    bridge = FakeBridge(before,
                        effects={"modifiers.apply": _readiness(0.9)},
                        preservation=0.5)
    out = finisher.finish(bridge, "subject", ITEM)
    move = next(m for m in out["moves"] if m["move"] == "decimate_to_budget")
    assert move["kept"] is False
    assert bridge.tools("session.revert")
    assert bridge.state == before  # harm undone despite the readiness gain


def test_erroring_move_reverts_and_continues():
    # uv.smart_unwrap explodes mid-move -> revert + record error; the later
    # transform move still runs and its fix is kept
    fixed = _readiness(0.6, ["uv.has_uvs"])
    bridge = FakeBridge(_readiness(0.5, ["uv.has_uvs", "scale.transform_applied"]),
                        effects={"object.transform_apply": fixed},
                        fail_tools={"uv.smart_unwrap"})
    out = finisher.finish(bridge, "subject", ITEM)
    errored = next(m for m in out["moves"] if m["move"] == "uv_unwrap")
    assert errored["kept"] is False and "error" in errored
    # the later transform move still ran, and its improvement was kept
    assert bridge.tools("object.transform_apply")
    transform = next(m for m in out["moves"] if m["move"] == "apply_transform")
    assert transform["kept"] is True
    assert bridge.state == fixed


def test_every_finisher_tool_is_registered():
    known = {("capabilities.invoke" if s.tier == "generated" else s.command)
             for s in build_router().specs()}
    missing = finisher.TOOLS_USED - known
    assert not missing, sorted(missing)
