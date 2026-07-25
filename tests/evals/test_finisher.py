"""The finisher's accept/revert loop, offline: a behavior-driven FakeBridge.

The FakeBridge holds a readiness STATE. Applying a tool named in `effects` transitions
the state; `session.revert` restores the pre-finish state (that is what revert means).
Tests assert behavior — state transitions and revert restoring state — never call-count
choreography.

Default finisher is bake_and_finish (bake-transfer + dual fail-closed harm axes).
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


def _pres(silhouette=1.0, fidelity=1.0):
    return {
        "available": True,
        "preservation": silhouette,
        "preservation_pass": silhouette >= 0.85,
        "surface_fidelity": {
            "available": True,
            "fidelity": fidelity,
            "surface_fidelity_pass": fidelity >= 0.60,
            "per_view": {},
            "min_view": {"view": "front", "ssim": fidelity},
        },
    }


class FakeBridge:
    """Behavior-driven bridge: readiness is a state; tools in `effects` transition it,
    session.revert restores the initial state. Preservation is fully measured by default
    so fail-closed harm gates can pass when scores are good."""

    def __init__(self, before, effects=None, preservation=1.0, fidelity=1.0,
                 fail_tools=(), preservation_response=None):
        self.before = before
        self.state = before
        self.effects = dict(effects or {})
        self.preservation = preservation
        self.fidelity = fidelity
        self.fail_tools = set(fail_tools)
        self.preservation_response = preservation_response  # override whole envelope
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
            if self.preservation_response is not None:
                return self.preservation_response
            return _pres(silhouette=self.preservation, fidelity=self.fidelity)
        if tool == "feedback.quality":
            return {"topology": {"tris": 100000},
                    "asset_class": {"effective_defaults": {"triangle_budget": 5000}}}
        if tool == "scene.info":
            return {"objects": [{"name": "subject", "type": "MESH"}]}
        return {}

    def tools(self, *names):
        return [c for c in self.calls if c[0] in names]


ITEM = {"id": "t", "asset_class": "hard_surface_prop"}


def test_default_finisher_is_bake_and_finish():
    assert "object.bake_transfer" in finisher.TOOLS_USED
    assert "object.retopo" in finisher.TOOLS_USED
    assert finisher.SURFACE_FIDELITY_FLOOR == 0.60


def test_move_skipped_when_its_gates_pass():
    bridge = FakeBridge(_readiness(1.0))
    out = finisher.finish(bridge, "subject", ITEM)
    assert out["moves"] == []
    assert bridge.tools("session.checkpoint") == []
    assert bridge.state == _readiness(1.0)  # untouched


def test_improving_move_is_kept():
    # transform gate failing; applying transform_apply transitions readiness 0.5 -> 0.7
    improved = _readiness(0.7)
    bridge = FakeBridge(_readiness(0.5, ["scale.transform_applied"]),
                        effects={"object.transform_apply": improved})
    out = finisher.finish(bridge, "subject", ITEM)
    kept = [m for m in out["moves"] if m["move"] == "apply_transform"]
    assert kept and kept[0]["kept"] is True
    assert bridge.tools("session.revert") == []
    assert bridge.tools("object.transform_apply")
    assert bridge.state == improved
    assert out["readiness_final"] == 0.7


def test_regressing_move_is_reverted():
    before = _readiness(0.5, ["scale.transform_applied"])
    bridge = FakeBridge(before,
                        effects={"object.transform_apply": _readiness(0.3, ["scale.transform_applied"])})
    out = finisher.finish(bridge, "subject", ITEM)
    move = next(m for m in out["moves"] if m["move"] == "apply_transform")
    assert move["kept"] is False
    reverts = bridge.tools("session.revert")
    assert reverts and reverts[0][1]["label"] == "finisher:apply_transform"
    assert bridge.state == before
    assert out["readiness_final"] == 0.5


def test_harm_below_preservation_floor_reverts_even_if_readiness_rose():
    # bake_retopo raises readiness 0.5 -> 0.9 but silhouette is 0.5 < 0.85 -> revert
    before = _readiness(0.5, ["engine.within_triangle_budget"])
    bridge = FakeBridge(before,
                        effects={"object.retopo": _readiness(0.9)},
                        preservation=0.5, fidelity=0.95)
    out = finisher.finish(bridge, "subject", ITEM)
    move = next(m for m in out["moves"] if m["move"] == "bake_retopo")
    assert move["kept"] is False
    assert bridge.tools("session.revert")
    assert bridge.state == before


def test_unmeasured_preservation_fail_closed_reverts():
    """Headless / no-GL: available:false must REVERT, never silent keep."""
    before = _readiness(0.5, ["scale.transform_applied"])
    bridge = FakeBridge(
        before,
        effects={"object.transform_apply": _readiness(0.9)},
        preservation_response={"available": False, "preservation": None,
                               "reason": "no opengl", "surface_fidelity": {"available": False}},
    )
    out = finisher.finish(bridge, "subject", ITEM)
    move = next(m for m in out["moves"] if m["move"] == "apply_transform")
    assert move["kept"] is False
    assert move["preservation"] is None
    assert bridge.tools("session.revert")
    assert bridge.state == before


def test_erroring_move_reverts_and_continues():
    # object.lod_create explodes mid-move -> revert + record error; the later
    # transform move still runs and its fix is kept
    fixed = _readiness(0.6, ["engine.has_lods"])
    bridge = FakeBridge(
        _readiness(0.5, ["engine.has_lods", "engine.lod_triangle_reduction_ok",
                         "engine.lod_silhouette_preserved", "scale.transform_applied"]),
        effects={"object.transform_apply": fixed},
        fail_tools={"object.lod_create"},
    )
    out = finisher.finish(bridge, "subject", ITEM)
    errored = next(m for m in out["moves"] if m["move"] == "lod")
    assert errored["kept"] is False and "error" in errored
    assert bridge.tools("object.transform_apply")
    transform = next(m for m in out["moves"] if m["move"] == "apply_transform")
    assert transform["kept"] is True
    assert bridge.state == fixed


def test_every_finisher_tool_is_registered():
    known = {("capabilities.invoke" if s.tier == "generated" else s.command)
             for s in build_router().specs()}
    missing = finisher.TOOLS_USED - known
    assert not missing, sorted(missing)


def test_all_reverted_moves_leave_readiness_final_at_intake():
    """Control-state hygiene: if every move reverts, readiness_final must not climb."""
    before = _readiness(0.36, ["engine.within_triangle_budget", "scale.transform_applied",
                               "engine.has_lods", "engine.lod_triangle_reduction_ok",
                               "engine.lod_silhouette_preserved",
                               "engine.has_collision_proxy", "engine.has_collision_hulls",
                               "engine.collision_bounds_valid",
                               "material.pbr_maps_present", "material.bake_maps_present",
                               "material.data_maps_non_color", "material.textures_within_size",
                               "material.atlas_ready"])
    # Every move improves measured readiness but harm is unmeasured -> all revert.
    bridge = FakeBridge(
        before,
        effects={
            "object.retopo": _readiness(0.40),
            "modifiers.apply": _readiness(0.40),
            "shading.prepare_pbr_maps": _readiness(0.52),
            "object.lod_create": _readiness(0.64),
            "object.collision_proxy_create": _readiness(0.64),
            "object.transform_apply": _readiness(0.70),
        },
        preservation_response={"available": False, "preservation": None,
                               "surface_fidelity": {"available": False}},
    )
    out = finisher.finish(bridge, "subject", ITEM)
    assert out["moves"] and all(m["kept"] is False for m in out["moves"])
    assert out["readiness_final"] == 0.36
