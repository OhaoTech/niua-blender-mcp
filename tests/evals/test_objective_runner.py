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
