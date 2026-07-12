"""The skills registry + make_game_ready ported onto the SDK, driven by a FakeSession."""

from __future__ import annotations

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.client import ToolSession
from niua_blender_mcp.domains import build_router
from niua_blender_mcp.finishing import skills
from niua_blender_mcp.finishing.skills import make_game_ready


def _readiness(score, failing=()):
    per_gate = [{"path": p, "op": "==", "value": True, "actual": False, "pass": False} for p in failing]
    per_gate.append({"path": "always.pass", "op": "==", "value": True, "actual": True, "pass": True})
    return {"readiness": score, "per_gate": per_gate}


class FakeBridge:
    """Behavior-driven: readiness is a state; tools in `effects` transition it; revert restores."""

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


ITEM_CLASS = "hard_surface_prop"


def test_registry_lists_make_game_ready_with_description():
    listed = {s["name"]: s for s in skills.list_skills()}
    assert "make_game_ready" in listed
    assert listed["make_game_ready"]["description"].strip()
    assert skills.get_skill("make_game_ready").name == "make_game_ready"


def test_improving_move_is_kept_via_sdk():
    seq = _readiness(0.5, ["uv.has_uvs"])
    after = _readiness(0.7)
    bridge = FakeBridge(before=seq, effects={"uv.smart_unwrap": after})
    session = ToolSession(bridge)
    report = make_game_ready.run(session, "subject", {"asset_class": ITEM_CLASS})
    kept = [m for m in report["moves"] if m["move"] == "uv_unwrap"]
    assert kept and kept[0]["kept"] is True
    assert not any(c[0] == "session.revert" for c in bridge.calls)


def test_regressing_move_is_reverted_via_sdk():
    bridge = FakeBridge(before=_readiness(0.5, ["uv.has_uvs"]),
                        effects={"uv.smart_unwrap": _readiness(0.3, ["uv.has_uvs"])})
    session = ToolSession(bridge)
    report = make_game_ready.run(session, "subject", {"asset_class": ITEM_CLASS})
    move = next(m for m in report["moves"] if m["move"] == "uv_unwrap")
    assert move["kept"] is False
    assert any(c[0] == "session.revert" for c in bridge.calls)


def test_all_tools_used_are_registered():
    known = {("capabilities.invoke" if s.tier == "generated" else s.command)
             for s in build_router().specs()}
    assert make_game_ready.TOOLS_USED <= known, sorted(make_game_ready.TOOLS_USED - known)


def test_finisher_delegates_to_skill_same_report_shape():
    # evals.finisher.finish still works and returns the same keys.
    from niua_blender_mcp.evals import finisher
    bridge = FakeBridge(before=_readiness(0.5, ["uv.has_uvs"]),
                        effects={"uv.smart_unwrap": _readiness(0.7)})
    report = finisher.finish(bridge, "subject", {"id": "t", "asset_class": ITEM_CLASS})
    assert set(report) == {"readiness_start", "readiness_final", "moves"}
