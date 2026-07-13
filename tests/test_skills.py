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


def _pres(silhouette=1.0, fidelity=1.0):
    return {"available": True, "preservation": silhouette, "preservation_pass": silhouette >= 0.85,
            "surface_fidelity": {"available": True, "fidelity": fidelity,
                                 "per_view": {}, "min_view": {"view": "front", "ssim": fidelity}}}


class FidelityBridge(FakeBridge):
    """FakeBridge whose feedback.preservation returns a scriptable surface_fidelity."""
    def __init__(self, *a, fidelity_after=1.0, **k):
        super().__init__(*a, **k)
        self.fidelity_after = fidelity_after
    def call(self, tool, payload):
        r = super().call(tool, payload)
        if tool == "feedback.preservation":
            fid = self.fidelity_after if self.state is not self.before else 1.0
            return _pres(silhouette=self.preservation, fidelity=fid)
        return r


def test_bake_and_finish_registered():
    from niua_blender_mcp.finishing import skills
    assert "bake_and_finish" in {s["name"] for s in skills.list_skills()}


def test_low_fidelity_bake_retopo_is_reverted_even_if_readiness_rose():
    from niua_blender_mcp.client import ToolSession
    from niua_blender_mcp.finishing.skills import bake_and_finish
    # object.retopo does NOT clear the triangle-budget gate here, so after bake_retopo
    # reverts, bake_decimate's gate is still failing and it fires too (also low fidelity).
    bridge = FidelityBridge(before=_readiness(0.4, ["engine.within_triangle_budget"]),
                            effects={"object.retopo": _readiness(0.6, ["engine.within_triangle_budget"])},
                            fidelity_after=0.5)
    session = ToolSession(bridge)
    report = bake_and_finish.run(session, "subject", {"asset_class": "hard_surface_prop"})
    retopo_move = next((m for m in report["moves"] if m["move"] == "bake_retopo"), None)
    assert retopo_move is not None and retopo_move["kept"] is False  # low fidelity forced a revert
    assert any(c[0] == "session.revert" for c in bridge.calls)


def test_bake_retopo_uses_retopo_not_decimate_when_kept():
    from niua_blender_mcp.client import ToolSession
    from niua_blender_mcp.finishing.skills import bake_and_finish
    # readiness marks the triangle-budget gate failing so bake_retopo fires; once kept,
    # the fake readiness clears that gate so bake_decimate's gate no longer fails -> skip.
    bridge = FidelityBridge(before=_readiness(0.4, ["engine.within_triangle_budget"]),
                            effects={"object.retopo": _readiness(0.6)}, fidelity_after=0.9)
    session = ToolSession(bridge)
    report = bake_and_finish.run(session, "subject", {"asset_class": "hard_surface_prop"})
    retopo_move = next(m for m in report["moves"] if m["move"] == "bake_retopo")
    assert retopo_move["kept"] is True
    decimate_move = next((m for m in report["moves"] if m["move"] == "bake_decimate"), None)
    assert decimate_move is None  # gate no longer failing -> move skipped entirely
    tools = [c[0] for c in bridge.calls]
    assert "object.retopo" in tools
    assert "modifiers.add" not in tools  # decimate path never ran
    assert "object.shrinkwrap" in tools  # snapped back onto the high-poly surface before unwrap
    # target_faces derived from the budget (5000 tris in the fake quality) -> ~2500 faces
    retopo_call = next(c for c in bridge.calls if c[0] == "object.retopo")
    assert retopo_call[1]["target_faces"] == 2500
    shrinkwrap_call = next(c for c in bridge.calls if c[0] == "object.shrinkwrap")
    assert shrinkwrap_call[1]["object"] == "subject"
    assert shrinkwrap_call[1]["target"] == "subject__high"
    unwrap_index = tools.index("uv.smart_unwrap")
    assert tools.index("object.shrinkwrap") < unwrap_index  # shrinkwrap runs before unwrap


def test_bake_decimate_fires_as_fallback_when_bake_retopo_reverts():
    """The best-of-both routing: when bake_retopo is reverted for low fidelity, the
    triangle-budget gate is still failing on the next move, so bake_decimate fires as
    the fallback reducer -- and if IT holds fidelity, it's kept instead."""
    from niua_blender_mcp.client import ToolSession
    from niua_blender_mcp.finishing.skills import bake_and_finish

    class RoutingBridge(FakeBridge):
        """object.retopo drops fidelity (organic mesh, thin features merged) but leaves
        the budget gate failing; modifiers.apply (decimate) hits budget AND holds fidelity."""
        def call(self, tool, payload):
            r = FakeBridge.call(self, tool, payload)
            if tool == "feedback.preservation":
                if self.state is self.before:
                    return _pres(silhouette=self.preservation, fidelity=1.0)
                after_decimate = any(c[0] == "modifiers.apply" for c in self.calls)
                fid = 0.9 if after_decimate else 0.2
                return _pres(silhouette=self.preservation, fidelity=fid)
            return r

    bridge = RoutingBridge(
        before=_readiness(0.4, ["engine.within_triangle_budget"]),
        effects={
            "object.retopo": _readiness(0.6, ["engine.within_triangle_budget"]),
            "modifiers.apply": _readiness(0.6),
        },
    )
    session = ToolSession(bridge)
    report = bake_and_finish.run(session, "subject", {"asset_class": "hard_surface_prop"})
    moves = {m["move"]: m for m in report["moves"]}
    assert "bake_retopo" in moves and moves["bake_retopo"]["kept"] is False
    assert "bake_decimate" in moves and moves["bake_decimate"]["kept"] is True
    tools = [c[0] for c in bridge.calls]
    assert "object.retopo" in tools
    assert "modifiers.add" in tools and "modifiers.apply" in tools
    # shrinkwrap fires for BOTH reducers via the shared _bake_with plumbing: once after
    # the reverted bake_retopo attempt, once after the kept bake_decimate attempt.
    assert tools.count("object.shrinkwrap") == 2


def test_retopo_in_tools_used_and_registered():
    from niua_blender_mcp.domains import build_router
    from niua_blender_mcp.finishing.skills import bake_and_finish
    assert "object.retopo" in bake_and_finish.TOOLS_USED
    assert "object.shrinkwrap" in bake_and_finish.TOOLS_USED
    known = {("capabilities.invoke" if s.tier == "generated" else s.command) for s in build_router().specs()}
    assert bake_and_finish.TOOLS_USED <= known


def test_bake_and_finish_all_tools_used_are_registered():
    from niua_blender_mcp.finishing.skills import bake_and_finish
    known = {("capabilities.invoke" if s.tier == "generated" else s.command)
             for s in build_router().specs()}
    assert bake_and_finish.TOOLS_USED <= known, sorted(bake_and_finish.TOOLS_USED - known)


def _pres_with_pass(silhouette, fidelity, sf_pass):
    """Like _pres, but with an addon-authoritative surface_fidelity_pass key present --
    exercises the PRIMARY path in _harm_ok (defers to the addon's own floor) rather than
    the SURFACE_FIDELITY_FLOOR fallback recomputation."""
    out = _pres(silhouette=silhouette, fidelity=fidelity)
    out["surface_fidelity"]["surface_fidelity_pass"] = sf_pass
    out["surface_fidelity"]["floor"] = 0.70  # a stricter addon-side floor than the 0.60 fallback
    return out


class FidelityPassBridge(FakeBridge):
    """FakeBridge whose feedback.preservation carries the primary surface_fidelity_pass key."""
    def __init__(self, *a, fidelity_after=1.0, sf_pass_after=True, **k):
        super().__init__(*a, **k)
        self.fidelity_after = fidelity_after
        self.sf_pass_after = sf_pass_after

    def call(self, tool, payload):
        r = super().call(tool, payload)
        if tool == "feedback.preservation":
            moved = self.state is not self.before
            fid = self.fidelity_after if moved else 1.0
            sf_pass = self.sf_pass_after if moved else True
            return _pres_with_pass(self.preservation, fid, sf_pass)
        return r


def test_surface_fidelity_pass_key_forces_revert_even_above_fallback_threshold():
    """fidelity=0.65 is ABOVE the 0.60 fallback SURFACE_FIDELITY_FLOOR, so if _harm_ok used
    the fallback numeric comparison this move would be kept. But the addon's authoritative
    surface_fidelity_pass=False must win -- proving the primary path (not the fallback) gates."""
    from niua_blender_mcp.client import ToolSession
    from niua_blender_mcp.finishing.skills import bake_and_finish
    bridge = FidelityPassBridge(before=_readiness(0.4, ["engine.within_triangle_budget"]),
                                effects={"object.retopo": _readiness(0.6)},
                                fidelity_after=0.65, sf_pass_after=False)
    session = ToolSession(bridge)
    report = bake_and_finish.run(session, "subject", {"asset_class": "hard_surface_prop"})
    move = next((m for m in report["moves"] if m["move"] == "bake_retopo"), None)
    assert move is not None and move["kept"] is False  # authoritative floor forced a revert
    assert any(c[0] == "session.revert" for c in bridge.calls)
