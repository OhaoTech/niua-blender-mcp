from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.domains import eyes


class _FakeBpyNoGPU:
    """Minimal fake: object exists, but rendering raises -> graceful degrade."""

    class data:
        class objects:
            @staticmethod
            def get(name):
                return object() if name == "Cube" else None

    class context:
        class scene:
            objects = []


def test_topology_degrades_gracefully_without_gpu():
    ctx = Ctx(_FakeBpyNoGPU())
    out = eyes.topology(ctx, {"object": "Cube"})
    assert out["available"] is False
    assert "reason" in out
    assert "Matrix" not in out["reason"]


def test_feedback_uv_and_orientation_are_registered():
    from niua_blender_mcp.domains import build_router
    from niua_mcp_bridge.domains import build_default_registry

    specs = {spec.name for spec in build_router().specs()}
    commands = build_default_registry().names()
    assert "feedback.uv" in specs
    assert "feedback.uv" in commands
    assert "feedback.orientation" in specs
    assert "feedback.orientation" in commands
