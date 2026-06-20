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
