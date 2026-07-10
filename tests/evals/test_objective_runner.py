from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_RUNNER = _REPO / "scripts" / "run_objective_benchmark.py"


def test_runner_parses() -> None:
    ast.parse(_RUNNER.read_text(encoding="utf-8"))


def _load_runner():
    sys.path.insert(0, str(_REPO / "scripts"))
    import run_objective_benchmark as runner  # noqa: E402 (path set above)

    return runner


def test_every_runner_and_recipe_tool_is_registered() -> None:
    # The heart of the red-team fix: no bad tool names reach the live path.
    from niua_blender_mcp.evals.benchmark import list_items, load_item

    runner = _load_runner()
    known = runner.known_tools()
    assert runner._RUNNER_TOOLS <= known, sorted(runner._RUNNER_TOOLS - known)
    # object.rename is the correct singular tool; objects.rename must NOT exist.
    assert "object.rename" in known
    assert "objects.rename" not in known
    for item_id in list_items():
        inp = load_item(item_id)["input"]
        if inp.get("asset"):
            # asset items import a fixture (io.import) + join multi-part via capabilities.invoke
            assert {"io.import", "capabilities.invoke"} <= known
            continue
        for step in inp["recipe"]:
            assert step["tool"] in known, step["tool"]


def test_registration_guard_passes_for_real_benchmark_items() -> None:
    from niua_blender_mcp.evals.benchmark import list_items, load_item

    runner = _load_runner()
    items = [load_item(item_id) for item_id in list_items()]
    runner.assert_tools_registered(items)  # must not raise


def test_registration_guard_fails_loud_offline_on_bad_tool_name() -> None:
    runner = _load_runner()
    bad_items = [{"id": "x", "input": {"recipe": [{"tool": "objects.rename", "args": {}}]}}]
    with pytest.raises(SystemExit):
        runner.assert_tools_registered(bad_items)


def test_build_input_diffs_scene_objects_not_a_nonexistent_active_key() -> None:
    """Source-level guard against CRITICAL #1 recurring: the runner must derive the newly
    created object's name from a before/after scene.info() diff -- never index a nonexistent
    "active" key on the scene.info() result."""
    text = _RUNNER.read_text(encoding="utf-8")
    assert '["active"]' not in text
    assert "['active']" not in text
    assert '.get("active"' not in text
    assert "objects" in text  # the actual diff key it does use


def test_no_op_finisher_is_honestly_scoped_as_a_baseline_probe() -> None:
    """Source-level guard against shipping a no-op driver that claims to test 'the pipeline
    preserves form' -- the default finisher's docstring must scope itself as an input-quality
    baseline probe, not a finishing-pipeline claim."""
    runner = _load_runner()
    doc = (runner._no_op_finisher.__doc__ or "") + runner.__doc__
    assert "baseline" in doc.lower()
    assert "input-quality" in doc.lower() or "input quality" in doc.lower()


def test_runner_tools_include_export_for_godot_roundtrip():
    runner = _load_runner()
    assert "io.export" in runner._RUNNER_TOOLS
    assert runner._RUNNER_TOOLS <= runner.known_tools()


def test_finisher_entrypoint_resolves():
    runner = _load_runner()
    fn, tools = runner._load_finisher("niua_blender_mcp.evals.finisher:finish")
    assert callable(fn)
    assert "feedback.readiness" in tools


def test_finisher_tools_are_known_to_the_runner_guard():
    from niua_blender_mcp.evals.finisher import TOOLS_USED
    runner = _load_runner()
    assert TOOLS_USED <= runner.known_tools(), sorted(TOOLS_USED - runner.known_tools())


def test_registration_guard_fails_loud_offline_when_finisher_declares_unregistered_tool() -> None:
    """A --finisher module's TOOLS_USED must be covered by the same offline guard as the
    runner's own tools -- a bogus tool name in a finisher must fail at startup, not mid-run."""
    from niua_blender_mcp.evals.benchmark import list_items, load_item

    runner = _load_runner()
    items = [load_item(item_id) for item_id in list_items()]
    with pytest.raises(SystemExit):
        runner.assert_tools_registered(items, extra_tools=frozenset({"objects.not_a_real_tool"}))


def test_registration_guard_passes_with_real_finisher_tools_used() -> None:
    from niua_blender_mcp.evals.benchmark import list_items, load_item
    from niua_blender_mcp.evals.finisher import TOOLS_USED

    runner = _load_runner()
    items = [load_item(item_id) for item_id in list_items()]
    runner.assert_tools_registered(items, extra_tools=frozenset(TOOLS_USED))  # must not raise


def test_run_item_scores_unmeasured_when_finisher_raises_bridge_error() -> None:
    """A BridgeError escaping the finisher must not abort the whole benchmark run -- the item
    scores UNMEASURED and run_item returns normally instead of propagating."""
    from niua_blender_mcp.bridge import BridgeError

    runner = _load_runner()

    class FakeBridge:
        def __init__(self):
            self.objects: list[dict] = []

        def call(self, tool, payload):
            if tool == "scene.info":
                return {"objects": list(self.objects)}
            if tool == "mesh.primitive_cube_add":
                self.objects.append({"name": "Cube", "type": "MESH"})
                return {}
            return {}

    item = {"id": "x", "asset_class": "hard_surface_prop",
            "input": {"recipe": [{"tool": "mesh.primitive_cube_add", "args": {}}]}}

    def bad_finisher(bridge, subject, item):
        raise BridgeError("internal_error", "boom")

    card = runner.run_item(FakeBridge(), item, bad_finisher, godot_fn=None)
    assert card["id"] == "x"
    assert card["readiness"] is None
    assert card["readiness_measured"] is False
    assert card["preservation_measured"] is False
